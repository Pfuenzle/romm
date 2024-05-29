from functools import cached_property
from datetime import datetime

from config import FRONTEND_RESOURCES_PATH
from models.assets import Save, Screenshot, State
from models.base import BaseModel
from sqlalchemy.dialects.mysql.json import JSON as MySQLJSON
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    BigInteger,
    DateTime,
    func,
    UniqueConstraint,
    select,
    and_,
    or_,
)
from sqlalchemy.orm import Mapped, relationship
from typing_extensions import TypedDict


class RomFile(TypedDict):
    filename: str
    crc_hash: str
    md5_hash: str
    sha1_hash: str


class Rom(BaseModel):
    __tablename__ = "roms"

    id = Column(Integer(), primary_key=True, autoincrement=True)

    igdb_id: int = Column(Integer())
    sgdb_id: int = Column(Integer())
    moby_id: int = Column(Integer())

    file_name: str = Column(String(length=450), nullable=False)
    file_name_no_tags: str = Column(String(length=450), nullable=False)
    file_name_no_ext: str = Column(String(length=450), nullable=False)
    file_extension: str = Column(String(length=100), nullable=False)
    file_path: str = Column(String(length=1000), nullable=False)
    file_size_bytes: int = Column(BigInteger(), default=0, nullable=False)

    name: str = Column(String(length=350))
    slug: str = Column(String(length=400))
    summary: str = Column(Text)
    igdb_metadata: MySQLJSON = Column(MySQLJSON, default=dict)
    moby_metadata: MySQLJSON = Column(MySQLJSON, default=dict)

    path_cover_s: str = Column(Text, default="")
    path_cover_l: str = Column(Text, default="")
    url_cover: str = Column(Text, default="", doc="URL to cover image stored in IGDB")

    revision: str = Column(String(100))
    regions: JSON = Column(JSON, default=[])
    languages: JSON = Column(JSON, default=[])
    tags: JSON = Column(JSON, default=[])

    path_screenshots: JSON = Column(JSON, default=[])
    url_screenshots: JSON = Column(
        JSON, default=[], doc="URLs to screenshots stored in IGDB"
    )

    multi: bool = Column(Boolean, default=False)
    files: list[RomFile] = Column(JSON, default=[])

    platform_id = Column(
        Integer(),
        ForeignKey("platforms.id", ondelete="CASCADE"),
        nullable=False,
    )

    platform = relationship("Platform", lazy="immediate")

    saves: Mapped[list[Save]] = relationship(
        "Save",
        back_populates="rom",
    )
    states: Mapped[list[State]] = relationship("State", back_populates="rom")
    screenshots: Mapped[list[Screenshot]] = relationship(
        "Screenshot", back_populates="rom"
    )
    notes: Mapped[list["RomNote"]] = relationship("RomNote", back_populates="rom")

    @property
    def platform_slug(self) -> str:
        return self.platform.slug

    @property
    def platform_fs_slug(self) -> str:
        return self.platform.fs_slug

    @property
    def platform_name(self) -> str:
        return self.platform.name

    @cached_property
    def full_path(self) -> str:
        return f"{self.file_path}/{self.file_name}"

    @cached_property
    def has_cover(self) -> bool:
        return bool(self.path_cover_s or self.path_cover_l)

    @cached_property
    def merged_screenshots(self) -> list[str]:
        return [s.download_path for s in self.screenshots] + [
            f"{FRONTEND_RESOURCES_PATH}/{s}" for s in self.path_screenshots
        ]

    # This is an expensive operation so don't call it on a list of roms
    def get_sibling_roms(self) -> list["Rom"]:
        from handler.database import db_rom_handler

        with db_rom_handler.session.begin() as session:
            return session.scalars(
                select(Rom).where(
                    and_(
                        Rom.platform_id == self.platform_id,
                        Rom.id != self.id,
                        or_(
                            and_(Rom.igdb_id == self.igdb_id, Rom.igdb_id != None),  # noqa
                            and_(Rom.moby_id == self.moby_id, Rom.moby_id != None),  # noqa
                        ),
                    )
                )
            ).all()

    # Metadata fields
    @property
    def alternative_names(self) -> list[str]:
        return (
            self.igdb_metadata.get("alternative_names", None)
            or self.moby_metadata.get("alternate_titles", None)
            or []
        )

    @property
    def first_release_date(self) -> int:
        return self.igdb_metadata.get("first_release_date", 0)

    @property
    def genres(self) -> list[str]:
        return (
            self.igdb_metadata.get("genres", None)
            or self.moby_metadata.get("genres", None)
            or []
        )

    @property
    def franchises(self) -> list[str]:
        return self.igdb_metadata.get("franchises", [])

    @property
    def collections(self) -> list[str]:
        return self.igdb_metadata.get("collections", [])

    @property
    def companies(self) -> list[str]:
        return self.igdb_metadata.get("companies", [])

    @property
    def game_modes(self) -> list[str]:
        return self.igdb_metadata.get("game_modes", [])

    def __repr__(self) -> str:
        return self.file_name


class RomNote(BaseModel):
    __tablename__ = "rom_notes"
    __table_args__ = (
        UniqueConstraint("rom_id", "user_id", name="unique_rom_user_note"),
    )

    id: int = Column(Integer(), primary_key=True, autoincrement=True)
    last_edited_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_markdown: str = Column(Text, nullable=False, default="")
    is_public: bool = Column(Boolean, default=False)

    rom_id: int = Column(
        Integer(),
        ForeignKey("roms.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: int = Column(
        Integer(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    rom = relationship("Rom", lazy="joined", back_populates="notes")
    user = relationship("User", lazy="joined", back_populates="notes")

    @property
    def user__username(self) -> str:
        return self.user.username
