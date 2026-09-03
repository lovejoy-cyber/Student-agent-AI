"""
Run with: python -m app.seed
Creates one sample university + one sample student so you can log in and test
the agent end to end before wiring up real data.
"""
from app.database import Base, engine, SessionLocal
from app.models import University, Student

Base.metadata.create_all(bind=engine)


def run():
    db = SessionLocal()
    try:
        existing = db.query(University).filter(University.name == "USTO-MB").first()
        if existing:
            print("Seed data already present, skipping.")
            return

        university = University(
            name="USTO-MB",
            city="Oran",
            grading_scale_config={"scale": 20, "pass_mark": 10, "rounding": "half_up"},
        )
        db.add(university)
        db.commit()
        db.refresh(university)

        student = Student(
            student_number="ZW-2024-001",
            full_name="Test Student",
            phone_number="+213500000000",
            university_id=university.id,
            programme="Aeronautical Engineering",
            academic_year="L3",
            status="active",
        )
        db.add(student)
        db.commit()

        print("Seed complete.")
        print(f"  University: {university.name} ({university.id})")
        print(f"  Student: {student.full_name}, phone={student.phone_number}, student_number={student.student_number}")
        print("  Use /auth/student/request-otp with this phone number to log in (check console for the OTP).")
    finally:
        db.close()


if __name__ == "__main__":
    run()
