import emoji
import socketio  # type: ignore
from rq import Worker
from rq.job import Job
from endpoints.responses.platform import PlatformSchema
from endpoints.responses.rom import RomSchema
from endpoints.responses.firmware import FirmwareSchema
from exceptions.fs_exceptions import (
    FolderStructureNotMatchException,
    RomsNotFoundException,
    FirmwareNotFoundException,
)
from config import SCAN_TIMEOUT
from handler.database import (
    db_rom_handler,
    db_firmware_handler,
    db_platform_handler,
)
from handler.filesystem import (
    fs_rom_handler,
    fs_firmware_handler,
    fs_platform_handler,
)
from handler.socket_handler import socket_handler
from handler.redis_handler import high_prio_queue, redis_url, redis_client
from handler.scan_handler import (
    scan_platform,
    scan_rom,
    scan_firmware,
    ScanType,
)
from handler.metadata.igdb_handler import IGDB_API_ENABLED
from handler.metadata.moby_handler import MOBY_API_ENABLED
from logger.logger import log


class ScanStats:
    def __init__(self):
        self.scanned_platforms = 0
        self.added_platforms = 0
        self.metadata_platforms = 0
        self.scanned_roms = 0
        self.added_roms = 0
        self.metadata_roms = 0
        self.scanned_firmware = 0
        self.added_firmware = 0


def _get_socket_manager():
    # Connect to external socketio server
    return socketio.AsyncRedisManager(redis_url, write_only=True)


async def scan_platforms(
    platform_ids: list[int],
    scan_type: ScanType = ScanType.QUICK,
    selected_roms: list[str] | None = None,
    metadata_sources: list[str] | None = None,
):
    """Scan all the listed platforms and fetch metadata from different sources

    Args:
        platform_slugs (list[str]): List of platform slugs to be scanned
        scan_type (str): Type of scan to be performed. Defaults to "quick".
        selected_roms (list[str], optional): List of selected roms to be scanned. Defaults to [].
        metadata_sources (list[str], optional): List of metadata sources to be used. Defaults to all sources.
    """

    sm = _get_socket_manager()

    if selected_roms is None:
        selected_roms = []

    if metadata_sources is None:
        metadata_sources = ["igdb", "moby"]

    if not IGDB_API_ENABLED and not MOBY_API_ENABLED:
        log.error("Search error: No metadata providers enabled")
        await sm.emit("scan:done_ko", "No metadata providers enabled")
        return

    try:
        fs_platforms: list[str] = fs_platform_handler.get_platforms()
    except FolderStructureNotMatchException as e:
        log.error(e)
        await sm.emit("scan:done_ko", e.message)
        return

    scan_stats = ScanStats()

    try:
        platform_list = [
            db_platform_handler.get_platforms(s).fs_slug for s in platform_ids
        ] or fs_platforms

        if len(platform_list) == 0:
            log.warn(
                "⚠️ No platforms found, verify that the folder structure is right and the volume is mounted correctly "
            )
        else:
            log.info(f"Found {len(platform_list)} platforms in file system ")

        for platform_slug in platform_list:
            platform = db_platform_handler.get_platform_by_fs_slug(platform_slug)
            if platform and scan_type == ScanType.NEW_PLATFORMS:
                continue

            scanned_platform = scan_platform(platform_slug, fs_platforms)
            if platform:
                scanned_platform.id = platform.id
                # Keep the existing ids if they exist on the platform
                scanned_platform.igdb_id = scanned_platform.igdb_id or platform.igdb_id
                scanned_platform.moby_id = scanned_platform.moby_id or platform.moby_id

            scan_stats.scanned_platforms += 1
            scan_stats.added_platforms += 1 if not platform else 0
            scan_stats.metadata_platforms += (
                1 if scanned_platform.igdb_id or scanned_platform.moby_id else 0
            )

            platform = db_platform_handler.add_platform(scanned_platform)

            await sm.emit(
                "scan:scanning_platform",
                PlatformSchema.model_validate(platform).model_dump(),
            )

            # Scanning firmware
            try:
                fs_firmware = fs_firmware_handler.get_firmware(platform)
            except FirmwareNotFoundException:
                fs_firmware = []

            if len(fs_firmware) == 0:
                log.warning(
                    "  ⚠️ No firmware found, skipping firmware scan for this platform"
                )
            else:
                log.info(f"  {len(fs_firmware)} firmware files found")

            for fs_fw in fs_firmware:
                firmware = db_firmware_handler.get_firmware_by_filename(
                    platform.id, fs_fw
                )

                scanned_firmware = scan_firmware(
                    platform=platform,
                    file_name=fs_fw,
                    firmware=firmware,
                )

                scan_stats.scanned_firmware += 1
                scan_stats.added_firmware += 1 if not firmware else 0

                _added_firmware = db_firmware_handler.add_firmware(scanned_firmware)
                firmware = db_firmware_handler.get_firmware(_added_firmware.id)

                await sm.emit(
                    "scan:scanning_firmware",
                    {
                        "platform_name": platform.name,
                        "platform_slug": platform.slug,
                        **FirmwareSchema.model_validate(firmware).model_dump(),
                    },
                )

            # Scanning roms
            try:
                fs_roms = fs_rom_handler.get_roms(platform)
            except RomsNotFoundException as e:
                log.error(e)
                continue

            if len(fs_roms) == 0:
                log.warning(
                    "  ⚠️ No roms found, verify that the folder structure is correct"
                )
            else:
                log.info(f"  {len(fs_roms)} roms found")

            for fs_rom in fs_roms:
                rom = db_rom_handler.get_rom_by_filename(
                    platform.id, fs_rom["file_name"]
                )

                # This logic is tricky so only touch it if you know what you're doing
                should_scan_rom = (
                    (scan_type == ScanType.NEW_PLATFORMS and not rom)
                    or (scan_type == ScanType.QUICK and not rom)
                    or (
                        scan_type == ScanType.UNIDENTIFIED
                        and rom
                        and not rom.igdb_id
                        and not rom.moby_id
                    )
                    or (
                        scan_type == ScanType.PARTIAL
                        and rom
                        and (not rom.igdb_id or not rom.moby_id)
                    )
                    or (scan_type == ScanType.COMPLETE)
                    or rom.id in selected_roms
                )

                if should_scan_rom:
                    scanned_rom = await scan_rom(
                        platform=platform,
                        rom_attrs=fs_rom,
                        scan_type=scan_type,
                        rom=rom,
                        metadata_sources=metadata_sources,
                    )

                    scan_stats.scanned_roms += 1
                    scan_stats.added_roms += 1 if not rom else 0
                    scan_stats.metadata_roms += (
                        1 if scanned_rom.igdb_id or scanned_rom.moby_id else 0
                    )

                    _added_rom = db_rom_handler.add_rom(scanned_rom)
                    rom = db_rom_handler.get_roms(_added_rom.id)

                    await sm.emit(
                        "scan:scanning_rom",
                        {
                            "platform_name": platform.name,
                            "platform_slug": platform.slug,
                            **RomSchema.model_validate(rom).model_dump(),
                        },
                    )

            db_rom_handler.purge_roms(
                platform.id, [rom["file_name"] for rom in fs_roms]
            )
            db_firmware_handler.purge_firmware(platform.id, [fw for fw in fs_firmware])
        db_platform_handler.purge_platforms(fs_platforms)

        log.info(emoji.emojize(":check_mark:  Scan completed "))
        await sm.emit("scan:done", scan_stats.__dict__)
    except Exception as e:
        log.error(e)
        # Catch all exceptions and emit error to the client
        await sm.emit("scan:done_ko", str(e))
        return


@socket_handler.socket_server.on("scan")
async def scan_handler(_sid: str, options: dict):
    """Scan socket endpoint

    Args:
        options (dict): Socket options
    """

    log.info(emoji.emojize(":magnifying_glass_tilted_right: Scanning "))

    platform_ids = options.get("platforms", [])
    scan_type = ScanType[options.get("type", "quick").upper()]
    selected_roms = options.get("roms", [])
    metadata_sources = options.get("apis", [])

    # Run in worker if redis is available
    return high_prio_queue.enqueue(
        scan_platforms,
        platform_ids,
        scan_type,
        selected_roms,
        metadata_sources,
        job_timeout=SCAN_TIMEOUT,  # Timeout after 4 hours
    )


@socket_handler.socket_server.on("scan:stop")
async def stop_scan_handler(_sid: str):
    """Stop scan socket endpoint"""

    log.info(emoji.emojize(":stop_button: Stopping scan..."))

    async def cancel_job(job: Job):
        job.cancel()
        log.info(emoji.emojize(":stop_button: Scan stopped"))

        sm = _get_socket_manager()
        await sm.emit("scan:done_ko", "manually stopped")

    existing_jobs = high_prio_queue.get_jobs()
    for job in existing_jobs:
        if job.func_name == "scan_platform" and job.is_started:
            return await cancel_job(job)

    workers = Worker.all(connection=redis_client)
    for worker in workers:
        current_job = worker.get_current_job()
        if (
            current_job
            and current_job.func_name == "endpoints.sockets.scan.scan_platforms"
            and current_job.is_started
        ):
            return await cancel_job(current_job)

    log.info(emoji.emojize(":stop_button: No running scan to stop"))
