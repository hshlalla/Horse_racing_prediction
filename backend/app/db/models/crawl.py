import datetime
from typing import Optional
from sqlalchemy import (
    Boolean, Integer, Date, DateTime, Float, ForeignKey,
    String, Text, UniqueConstraint, func, text, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Horse(Base):
    __tablename__ = "horses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sex: Mapped[str] = mapped_column(String(1))  # M/F/G
    age: Mapped[Optional[int]] = mapped_column(Integer)
    breed_origin: Mapped[Optional[str]] = mapped_column(String(20))
    import_year: Mapped[Optional[int]] = mapped_column(Integer)
    last_start_training_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    last_start_training_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class Jockey(Base):
    __tablename__ = "jockeys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kra_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True)


class Trainer(Base):
    __tablename__ = "trainers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kra_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True)


class Pedigree(Base):
    __tablename__ = "pedigree"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), unique=True)
    sire_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("horses.id"))
    dam_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("horses.id"))
    sire_sire_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("horses.id"))


class Race(Base):
    __tablename__ = "races"
    __table_args__ = (UniqueConstraint("track", "race_date", "race_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track: Mapped[str] = mapped_column(String(10))  # SEOUL/BUSAN/JEJU
    race_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    race_number: Mapped[int] = mapped_column(Integer, nullable=False)
    race_name: Mapped[str] = mapped_column(String(200))
    distance_m: Mapped[int] = mapped_column(Integer)
    surface: Mapped[str] = mapped_column(String(20))
    track_condition: Mapped[Optional[str]] = mapped_column(String(20))
    weather: Mapped[Optional[str]] = mapped_column(String(20))
    humidity: Mapped[Optional[int]] = mapped_column(Integer)
    grade: Mapped[Optional[str]] = mapped_column(String(10))
    race_class: Mapped[Optional[str]] = mapped_column(String(50))
    field_size: Mapped[Optional[int]] = mapped_column(Integer)
    post_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    video_url: Mapped[Optional[str]] = mapped_column(String(200))
    payouts: Mapped[Optional[dict]] = mapped_column(JSON)

    entries: Mapped[list["RaceEntry"]] = relationship(back_populates="race")


class RaceEntry(Base):
    __tablename__ = "race_entries"
    __table_args__ = (UniqueConstraint("race_id", "program_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    jockey_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jockeys.id"))
    trainer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("trainers.id"))
    program_number: Mapped[int] = mapped_column(Integer)
    carry_weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    body_weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    morning_odds: Mapped[Optional[float]] = mapped_column(Float)
    market_fav_rank: Mapped[Optional[int]] = mapped_column(Integer)  # 당일 인기순위 1/2/3, else NULL

    race: Mapped["Race"] = relationship(back_populates="entries")
    horse: Mapped["Horse"] = relationship()
    jockey: Mapped["Jockey"] = relationship()
    trainer: Mapped["Trainer"] = relationship()


class RaceResult(Base):
    __tablename__ = "race_results"
    __table_args__ = (UniqueConstraint("race_id", "horse_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    finish_position: Mapped[Optional[int]] = mapped_column(Integer)
    finish_time_s: Mapped[Optional[float]] = mapped_column(Float)
    final_odds: Mapped[Optional[float]] = mapped_column(Float)
    margin_lengths: Mapped[Optional[float]] = mapped_column(Float)


class InraceTiming(Base):
    __tablename__ = "inrace_timings"
    __table_args__ = (UniqueConstraint("race_id", "horse_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    s1f_time: Mapped[Optional[float]] = mapped_column(Float)
    g3f_time: Mapped[Optional[float]] = mapped_column(Float)
    corner1_rank: Mapped[Optional[int]] = mapped_column(Integer)
    corner2_rank: Mapped[Optional[int]] = mapped_column(Integer)
    corner3_rank: Mapped[Optional[int]] = mapped_column(Integer)
    corner4_rank: Mapped[Optional[int]] = mapped_column(Integer)
    corner5_rank: Mapped[Optional[int]] = mapped_column(Integer)
    corner6_rank: Mapped[Optional[int]] = mapped_column(Integer)
    corner7_rank: Mapped[Optional[int]] = mapped_column(Integer)


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    snapshot_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    win_odds: Mapped[Optional[float]] = mapped_column(Float)
    place_odds: Mapped[Optional[float]] = mapped_column(Float)


class WorkoutTime(Base):
    __tablename__ = "workout_times"
    __table_args__ = (UniqueConstraint("horse_id", "workout_date", "distance_m"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    workout_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    workout_type: Mapped[Optional[str]] = mapped_column(String(20))  # 주행심사/실기심사
    distance_m: Mapped[int] = mapped_column(Integer, default=1000)
    time_s: Mapped[Optional[float]] = mapped_column(Float)   # seconds, e.g. 65.2 for 1:05.2
    rank: Mapped[Optional[int]] = mapped_column(Integer)     # rank in workout group
    group_size: Mapped[Optional[int]] = mapped_column(Integer)
    start_training_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    swim_count_recent: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class HealthRecord(Base):
    __tablename__ = "health_records"
    __table_args__ = (UniqueConstraint("horse_id", "record_date", "condition"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    record_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    condition: Mapped[Optional[str]] = mapped_column(String(50))
    count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class StartTrainingRecord(Base):
    __tablename__ = "start_training_records"
    __table_args__ = (UniqueConstraint("horse_id", "train_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    train_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    rider: Mapped[Optional[str]] = mapped_column(String(30))
    remark: Mapped[Optional[str]] = mapped_column(String(50))     # 양호/진입불량/출발자세불량 …
    passed: Mapped[Optional[bool]] = mapped_column(Boolean)       # 양호→True, *불량→False
    equipment: Mapped[Optional[str]] = mapped_column(String(50))  # 출발장구
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class PreRaceWorkout(Base):
    __tablename__ = "pre_race_workouts"
    __table_args__ = (UniqueConstraint("race_id", "horse_id", "day_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    day_label: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. "전주-월", "금주-토"
    rider: Mapped[Optional[str]] = mapped_column(String(30))
    count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class Scratching(Base):
    __tablename__ = "scratchings"
    __table_args__ = (UniqueConstraint("race_id", "horse_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(50))
    scratched_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))


class CrawlState(Base):
    __tablename__ = "crawl_state"
    __table_args__ = (UniqueConstraint("track"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track: Mapped[str] = mapped_column(String(10), nullable=False)
    last_crawled_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    last_status: Mapped[Optional[str]] = mapped_column(String(20))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP")
    )


class CrawlFailure(Base):
    __tablename__ = "crawl_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track: Mapped[str] = mapped_column(String(10), nullable=False)
    failed_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class RacePrediction(Base):
    __tablename__ = "race_predictions"
    __table_args__ = (UniqueConstraint("race_id", "horse_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(Integer, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int] = mapped_column(Integer, ForeignKey("horses.id"), nullable=False)
    win_probability: Mapped[float] = mapped_column(Float, nullable=False)
    place_probability: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    is_stale: Mapped[bool] = mapped_column(default=False)
