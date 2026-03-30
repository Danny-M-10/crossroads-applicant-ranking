import json
import logging

from google import genai
from google.genai import types

from app.branding import ORG_CONTEXT_FOR_AI
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert HR analyst and recruiter evaluating resumes for "
    + ORG_CONTEXT_FOR_AI
    + """

Your task is to objectively score a candidate's resume against specific job criteria. You must be fair, consistent, and evidence-based in your scoring.

SCORING RULES — use EXACT integer or half-point values only (e.g. 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
1. Score each criterion on a 0-10 scale using these STRICT definitions:
   - 0:   No evidence whatsoever in the resume
   - 1:   Mentioned once in passing, completely tangential
   - 2:   Slight indirect relevance only
   - 3:   Some related background but major gaps vs. the criterion
   - 4:   Partial match — meets roughly half the criterion
   - 5:   Meets the basic minimum expectation for the criterion
   - 6:   Solid match, meets expectations with minor gaps
   - 7:   Strong evidence, clearly exceeds basic expectations
   - 8:   Very strong — well above expectations with specific proof
   - 9:   Near-perfect match, extensive direct evidence
   - 10:  Exact, explicit, unambiguous match to the criterion (reserve for certifications explicitly listed or roles that are a perfect 1:1 match)

2. DECISION RULES to eliminate ambiguity:
   - If a license, certification, or qualification is EXPLICITLY named in the resume → score 10. If it is implied but not stated → score 5 maximum.
   - If a role title directly matches the criterion (e.g. "Route Driver" for Driving Experience) → minimum score 7.
   - If the criterion requires direct experience and the candidate has only adjacent/transferable experience → score 4 maximum.
   - When torn between two adjacent scores (e.g. 3 vs 4), always choose the LOWER score unless you can cite a specific line from the resume that justifies the higher score.

3. Base scores ONLY on what is explicitly stated in the resume text. Do NOT infer, assume, or give benefit of the doubt.

4. The candidate_name field should contain the candidate's full name as it appears on their resume. If no name is found, use "Unknown Candidate".

You MUST respond with valid JSON matching this exact schema:
{
  "candidate_name": "string",
  "scores": [
    {
      "criterion_name": "string (exact name from the criteria list)",
      "score": number (0-10, integers only),
      "justification": "string (1-2 sentences citing the EXACT resume text that determined the score)"
    }
  ],
  "summary": "string (2-3 sentence overall candidate profile)",
  "red_flags": ["string (any concerns: gaps, inconsistencies, missing qualifications)"]
}

Return ONLY valid JSON. No markdown, no extra text."""
)


def build_user_prompt(
    job_title: str, job_description: str, criteria: list[dict], resume_text: str
) -> str:
    criteria_block = "\n".join(
        f"- **{c['name']}** (Weight: {c['weight']}%): {c.get('description', '')}"
        for c in criteria
    )
    # Truncate very long resumes
    truncated = resume_text[:15000]
    return f"""EVALUATE THIS CANDIDATE FOR THE FOLLOWING ROLE:

## Job Role: {job_title}

## Job Description:
{job_description}

## Scoring Criteria (score each one 0-10):
{criteria_block}

## Candidate Resume:
---
{truncated}
---

Score this candidate against ALL of the criteria listed above. Respond with JSON only."""


def score_candidate_sync(
    job_title: str,
    job_description: str,
    criteria: list[dict],
    resume_text: str,
) -> dict:
    """Score a single candidate. Returns parsed JSON dict with scores."""
    client = genai.Client(api_key=settings.gemini_api_key)
    user_prompt = build_user_prompt(job_title, job_description, criteria, resume_text)

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=8192,
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    raw_text = response.text.strip()

    # Strip markdown code fences if the model wraps output despite response_mime_type
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines).strip()

    # Extract the first complete JSON object as a fallback for any leading/trailing noise
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        # Find the outermost { ... } block and try again
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_text[start:end + 1])
        raise


def compute_weighted_total(scores_data: dict, criteria: list[dict]) -> float:
    """Compute weighted total on a 0-100 scale."""
    criteria_weights = {c["name"]: c["weight"] for c in criteria}
    total = 0.0
    for cs in scores_data.get("scores", []):
        weight = criteria_weights.get(cs["criterion_name"], 0)
        total += cs["score"] * (weight / 100) * 10
    return round(total, 2)


def validate_scores(scores_data: dict, criteria: list[dict]) -> list[str]:
    """Return list of validation warnings."""
    warnings = []
    expected_names = {c["name"] for c in criteria}
    returned_names = {s["criterion_name"] for s in scores_data.get("scores", [])}

    missing = expected_names - returned_names
    if missing:
        warnings.append(f"Missing scores for criteria: {missing}")

    return warnings
