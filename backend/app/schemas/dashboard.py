from pydantic import BaseModel


class DashboardMetrics(BaseModel):
    comments_processed: int
    questions_detected: int
    existing_answers_found: int
    content_requests: int
    pending_replies: int
    published_replies: int
