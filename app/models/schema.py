from pydantic import BaseModel
from typing import Literal


class AnalyzeRequest(BaseModel):
    company_name: str


class AnalyzeResponse(BaseModel):
    company_name:          str
    company_summary:       str
    icp_industry:          str
    icp_scale:             str
    icp_fit:               Literal["High", "Medium", "Low"]
    icp_fit_reason:        str
    problem:               str
    problem_evidence:      str
    channeltalk_solution:  str
    decision_maker:        str
    decision_maker_reason: str
    notion_url:            str | None = None


class ErrorResponse(BaseModel):
    error:        str
    company_name: str
