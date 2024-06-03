from functools import cached_property
from typing import Optional

from models.base import BaseModel
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship


class BaseAsset(BaseModel):
    __abstract__ = True

    id = Column(Integer(), primary_key=True, autoincrement=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    file_name = Column(String(length=450), nullable=False)
    file_name_no_tags = Column(String(length=450), nullable=False)
    file_name_no_ext = Column(String(length=450), nullable=False)
    file_extension = Column(String(length=100), nullable=False)
    file_path = Column(String(length=1000), nullable=False)
    file_size_bytes = Column(BigInteger(), default=0, nullable=False)

    @cached_property
    def full_path(self) -> str:
        return f"{self.file_path}/{self.file_name}"

    @cached_property
    def download_path(self) -> str:
        return f"/api/raw/assets/{self.full_path}?timestamp={self.updated_at}"


class RomAsset(BaseAsset):
    __abstract__ = True

    rom_id = Column(
        Integer(), ForeignKey("roms.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Integer(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class Save(RomAsset):
    __tablename__ = "saves"
    __table_args__ = {"extend_existing": True}

    emulator = Column(String(length=50), nullable=True)

    rom = relationship("Rom", lazy="joined", back_populates="saves")
    user = relationship("User", lazy="joined", back_populates="saves")

    @cached_property
    def screenshot(self) -> Optional["Screenshot"]:
        from handler.database import db_rom_handler

        db_rom = db_rom_handler.get_roms(self.rom_id)
        for screenshot in db_rom.screenshots:
            if screenshot.file_name_no_ext == self.file_name:
                return screenshot

        return None


class State(RomAsset):
    __tablename__ = "states"
    __table_args__ = {"extend_existing": True}

    emulator = Column(String(length=50), nullable=True)

    rom = relationship("Rom", lazy="joined", back_populates="states")
    user = relationship("User", lazy="joined", back_populates="states")

    @cached_property
    def screenshot(self) -> Optional["Screenshot"]:
        from handler.database import db_rom_handler

        db_rom = db_rom_handler.get_roms(self.rom_id)
        for screenshot in db_rom.screenshots:
            if screenshot.file_name_no_ext == self.file_name:
                return screenshot

        return None


class Screenshot(RomAsset):
    __tablename__ = "screenshots"
    __table_args__ = {"extend_existing": True}

    rom = relationship("Rom", lazy="joined", back_populates="screenshots")
    user = relationship("User", lazy="joined", back_populates="screenshots")
