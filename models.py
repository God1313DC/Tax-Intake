from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ClientSubmission(db.Model):
    __tablename__ = "client_submissions"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Basic contact (no SSN / no docs)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    filing_year = db.Column(db.String(10), nullable=True)

    # Store all intake answers here (JSON string)
    answers_json = db.Column(db.Text, nullable=True)

    # Computed outputs for preparers
    flags_json = db.Column(db.Text, nullable=True)        # Likely/Possible/Unlikely + why
    request_docs_json = db.Column(db.Text, nullable=True) # What to request via email

