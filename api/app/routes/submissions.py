from fastapi import APIRouter, Depends, status, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from ..utils import oauth2
from ..utils.redis_utils import enqueue_job
from ..schemas.submissions import SubmissionCreate, SubmissionResponse, SubmissionHeaderResponse
from ..database import get_db

from shared.core import get_storage_submission_code
from shared.models import (
    User, # users
    EXTENSIONS, Verdict, # enums
    Submission, # submissions
    Problem # problems
)

router = APIRouter(
    prefix='/submissions',
    tags=['Submissions']
)

@router.post('/', status_code=status.HTTP_201_CREATED, response_model=SubmissionResponse)
def create_submission(details: SubmissionCreate, current_user: User = Depends(oauth2.get_current_user), db: Session = Depends(get_db)):

    problem = db.query(Problem).filter(Problem.id == details.problem_id, Problem.visibility == True).first()
    if not problem:
        raise HTTPException(detail="Problem with the given ID was not found", status_code=status.HTTP_404_NOT_FOUND)

    code_object_key = get_storage_submission_code().upload_bytes(
        extension=EXTENSIONS[details.language],
        data=details.code.encode("utf-8")
    )

    submission = Submission(
        language=details.language,
        code_object_key=code_object_key,
        problem_id=details.problem_id,
        user_id=current_user.id,
        verdict=Verdict.PENDING
    )

    db.add(submission)
    db.commit()
    db.refresh(submission)

    ##################################################
    # SEND TO JUDGE FOR VALIDATION
    ##################################################
    enqueue_job(submission.id)

    return {
        "id": submission.id,
        "language": submission.language,
        "submitted_at": submission.submitted_at,
        "problem_id": submission.problem_id,
        "username": submission.user.username,
        "verdict": submission.verdict,
        "incorrect_testcase": submission.incorrect_testcase,
        "output": submission.output,
        "walltime_ms": submission.walltime_ms,
        "memory_kb": submission.memory_kb,
        "code": details.code
    }

@router.get('/', status_code=status.HTTP_200_OK, response_model=List[SubmissionHeaderResponse])
def get_submissions(problem_id: str | None = None, username: str | None = None, page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=5, le=100), current_user: User | None = Depends(oauth2.get_optional_current_user), db: Session = Depends(get_db)):
    if not username and not current_user:
        raise HTTPException(detail="Username cannot be empty for non logged in users", status_code=status.HTTP_400_BAD_REQUEST)
    
    if username:
        user: User | None = db.query(User).filter(User.username == username).first()
    else:
        user: User | None = current_user
    
    if not user:
        raise HTTPException(detail="User with the given username was not found", status_code=status.HTTP_404_NOT_FOUND)
    
    if problem_id:
        problem = db.query(Problem).filter(Problem.id == problem_id, Problem.visibility == True).first()
        if problem:
            query = db.query(Submission).filter(Submission.user_id == user.id, Submission.problem_id == problem.id)
        else:
            raise HTTPException(detail="Problem with given ID was not found", status_code=status.HTTP_404_NOT_FOUND)
    else:
        query = db.query(Submission).join(Problem).filter(Submission.user_id == user.id, Problem.visibility == True)
    
    offset: int = (page - 1) * limit
    submissions = query.order_by(Submission.submitted_at.desc()).offset(offset).limit(limit).all()
    
    return submissions

@router.get('/{submission_id}', status_code=status.HTTP_200_OK, response_model=SubmissionResponse)
def get_submission_by_id(submission_id: int, db: Session = Depends(get_db)):

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission or submission.problem.visibility == False:
        raise HTTPException(detail="Submission not found", status_code=status.HTTP_404_NOT_FOUND)

    return {
        "id": submission.id,
        "language": submission.language,
        "submitted_at": submission.submitted_at,
        "problem_id": submission.problem_id,
        "username": submission.user.username,
        "verdict": submission.verdict,
        "incorrect_testcase": submission.incorrect_testcase,
        "output": submission.output,
        "walltime_ms": submission.walltime_ms,
        "memory_kb": submission.memory_kb,
        "code": submission.code
    }
