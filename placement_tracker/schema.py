from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime

class PlacementRecord(BaseModel):
    student_name: str = Field(description="Student full name", default="Unknown")
    student_id: str = Field(description="Roll number or student ID", default="")
    company_name: str = Field(description="Hiring company name", default="Unknown")
    offer_type: str = Field(description="Type of offer (e.g. Intern, Intern+FT, FT, PPO, N/A)", default="N/A")
    ctc: str = Field(description="The annual CTC or stipend (e.g., '13-16 LPA', '40k/month', 'N/A')", default="N/A")
    status: str = Field(description="Application status: Applied, Interviewing, Rejected, Shortlisted, Offered, N/A", default="N/A")

        
    @property
    def dedup_key(self) -> str:
        """
        Creates a unique deduplication key for this record.
        Uses roll number + company name. If roll number is absent, falls back to name.
        """
        identifier = self.student_id.lower().strip() if self.student_id else self.student_name.lower().strip()
        comp = self.company_name.lower().strip()
        return f"{identifier}::{comp}"

    def to_sheet_row(self) -> list:
        """
        Converts the record to a list of values for Google Sheets in a fixed column order.
        Order: student_name | student_id | company_name | offer_type | ctc | email_date
        """
        return [
            self.student_name,
            self.student_id or "",
            self.company_name,
            self.offer_type,
            self.ctc or "",
            self.status or "",
        ]
