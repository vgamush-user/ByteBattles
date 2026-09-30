import io
import json
import zipfile
from pydantic import ValidationError

from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, Form, File, Query
from sqlalchemy.orm import Session
from typing import List, Dict, BinaryIO

from ..schemas.problems import (
    ProblemResponse,
    ProblemDetailResponse,
    ProblemListResponse,
    ProblemArrayDataValidator,
    TagCreate,
    ProblemCreateResponse,
    ProblemUpdate
)
from ..utils import oauth2
from ..database import get_db

from shared.core import get_storage_testcases, get_storage_submission_code
from shared.models import (
    Problem, Category, TestCase, # problems
    Submission, # submissions
    User, # users
    Difficulty # enums
)

router = APIRouter(
    prefix='/problems',
    tags=["Problems"]
)

@router.post('/tag', status_code=status.HTTP_201_CREATED)
def create_tag(tag: TagCreate, current_user: User = Depends(oauth2.get_current_admin), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.slug == tag.slug).first()
    if category:
        raise HTTPException(detail="Tag with given slug already exists", status_code=status.HTTP_400_BAD_REQUEST)
    category = Category(name=tag.name, slug=tag.slug)
    db.add(category)
    db.commit()
    db.refresh(category)
    return {"name": category.name, "slug": category.slug}

@router.get('/', status_code=status.HTTP_200_OK, response_model=ProblemListResponse)
def get_problems(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    title: str | None = Query(default=None, description="Search by problem title"),
    difficulty: Difficulty | None = Query(default=None, description="Filter by difficulty"),
    tag: str | None = Query(default=None, description="Filter by tag slug"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(oauth2.get_optional_current_admin)
):
    query = db.query(Problem)
    if not current_user:
        query = query.filter(Problem.visibility == True)

    if title:
        query = query.filter(Problem.title.ilike(f"%{title}%"))

    if difficulty:
        query = query.filter(Problem.difficulty == difficulty)

    if tag:
        query = query.join(Problem.tags).filter(Category.slug == tag)

    total = query.distinct().count() if tag else query.count()
    offset = (page - 1) * limit
    problems = query.order_by(Problem.id.asc()).offset(offset).limit(limit).all()

    items = [
        {
            "id": problem.id,
            "title": problem.title,
            "difficulty": problem.difficulty,
            "tags": [t.slug for t in problem.tags],
            "accepted_submissions": problem.accepted_submissions or 0,
            "total_submissions": problem.total_submissions or 0
        }
        for problem in problems
    ]

    has_more = (offset + len(problems)) < total

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "has_more": has_more
    }

@router.get('/{problem_id}', status_code=status.HTTP_200_OK, response_model=ProblemDetailResponse)
def get_problem_by_id(problem_id: str, db: Session = Depends(get_db), current_user: User | None = Depends(oauth2.get_optional_current_admin)):
    if current_user:
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
    else:
        problem = db.query(Problem).filter(Problem.id == problem_id, Problem.visibility == True).first()
    
    if not problem:
        raise HTTPException(detail="requested problem doesn't exist", status_code=status.HTTP_404_NOT_FOUND)
    
    return {
        "id": problem.id,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "tags": [tag.slug for tag in problem.tags],
        "accepted_submissions": problem.accepted_submissions or 0,
        "total_submissions": problem.total_submissions or 0,

        "description": problem.description,
        "constraints": problem.constraints,
        "input_desc": problem.input_desc,
        "output_desc": problem.output_desc,
        "sample_io": problem.sample_io,
        "explanation": problem.explanation,

        "memory_limit_mb": problem.memory_limit_mb,
        "time_limit_sec": problem.time_limit_sec,

        "source": problem.source,
        "editorial": problem.editorial,
        "visibility": problem.visibility
    }

@router.post('/', status_code=status.HTTP_201_CREATED, response_model=ProblemCreateResponse)
async def create_problem(
    id: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    difficulty: Difficulty = Form(...),
    constraints: str = Form(...),
    tags: str = Form(...),
    sample_io: str = Form(...),

    input_desc: str = Form(...),
    output_desc: str = Form(...),
    explanation: str | None = Form(None),

    memory_limit_mb: int = Form(...),
    time_limit_sec: int = Form(...),

    visibility: bool = Form(False),
    source: str | None = Form(None),
    editorial: str | None = Form(None),

    tests_zip: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(oauth2.get_current_admin)
):
    
    # Validating Problem Id
    problem = db.query(Problem).filter(Problem.id == id).first()
    if problem:
        raise HTTPException(detail="Problem with key already exists", status_code=status.HTTP_400_BAD_REQUEST)
    
    # Validate Zip Files
    if not tests_zip.filename.endswith(".zip"):
        raise HTTPException(detail="Only ZIP files are allowed", status_code=status.HTTP_400_BAD_REQUEST)

    zip_bytes = await tests_zip.read()

    try:
        zip_file = zipfile.ZipFile(
            io.BytesIO(zip_bytes)
        )
    except zipfile.BadZipFile:
        raise HTTPException(detail="Invalid ZIP file", status_code=status.HTTP_400_BAD_REQUEST)

    # Validate Required Folders
    all_files = zip_file.namelist()
    prefix = tests_zip.filename.split(".")[0]

    input_files = sorted([
        f for f in all_files
        if f.startswith(prefix + "/inputs/")
        and not f.endswith("/")
    ])

    output_files = sorted([
        f for f in all_files
        if f.startswith(prefix + "/outputs/")
        and not f.endswith("/")
    ])

    if not input_files or not output_files:
        zip_file.close()
        raise HTTPException(detail="ZIP must contain inputs/ and outputs/", status_code=status.HTTP_400_BAD_REQUEST)
    if len(input_files) != len(output_files):
        zip_file.close()
        raise HTTPException(detail="Mismatch between input and output files", status_code=status.HTTP_400_BAD_REQUEST)
    
    for input_file, output_file in zip(input_files, output_files):
        if input_file.split("/")[-1] != output_file.split("/")[-1]:
            zip_file.close()
            raise HTTPException(detail="Mismatch in input and output file name. Each input file should have a corespoinding output file", status_code=status.HTTP_400_BAD_REQUEST)
    
    # Validating Array Data
    try:
        array_data = ProblemArrayDataValidator(
            tags=json.loads(tags),
            constraints=json.loads(constraints),
            sample_io=json.loads(sample_io)
        )
    except (json.JSONDecodeError, ValidationError):
        zip_file.close()
        raise HTTPException(detail="Invalid format for tags, constraints, or sample_io", status_code=status.HTTP_400_BAD_REQUEST)
    
    categories = db.query(Category).filter(Category.slug.in_(array_data.tags)).all()
    if len(categories) != len(array_data.tags):
        zip_file.close()
        raise HTTPException(detail="One or more tags are invalid", status_code=status.HTTP_400_BAD_REQUEST)

    # Create Problem
    problem = Problem(
        id=id,
        title=title,
        description=description,
        difficulty=difficulty,

        constraints=array_data.constraints,
        tags=categories,
        sample_io=array_data.sample_io,

        input_desc=input_desc,
        output_desc=output_desc,
        explanation=explanation,

        memory_limit_mb=memory_limit_mb,
        time_limit_sec=time_limit_sec,

        visibility=visibility,
        source=source,
        editorial=editorial
    )

    try:
        db.add(problem)
        db.flush()

        # Upload Testcases
        for input_path, output_path in zip(
            input_files,
            output_files
        ):
            input_data = zip_file.read(input_path)
            output_data = zip_file.read(output_path)

            input_key = get_storage_testcases().upload_bytes(
                problem_id=problem.id,
                filename=input_path.split("/")[-1],
                data=input_data
            )

            output_key = get_storage_testcases().upload_bytes(
                problem_id=problem.id,
                filename=output_path.split("/")[-1],
                data=output_data
            )

            testcase = TestCase(
                problem_id=problem.id,
                input_key=input_key,
                output_key=output_key
            )
            db.add(testcase)
        
        db.commit()
    except Exception:
        db.rollback()
        get_storage_testcases().delete_problem_folder(problem.id)
        raise HTTPException(detail="Unknown Error Occurred", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        zip_file.close()

    return {
        "id": problem.id,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "tags": [category.slug for category in problem.tags],
        "testcases": len(input_files)
    }

@router.patch('/{problem_id}', status_code=status.HTTP_200_OK, response_model=ProblemDetailResponse)
@router.put('/{problem_id}', status_code=status.HTTP_200_OK, response_model=ProblemDetailResponse)
async def update_problem(
    problem_id: str,
    title: str | None = Form(None),
    description: str | None = Form(None),
    difficulty: Difficulty | None = Form(None),
    constraints: str | None = Form(None),
    tags: str | None = Form(None),
    sample_io: str | None = Form(None),

    input_desc: str | None = Form(None),
    output_desc: str | None = Form(None),
    explanation: str | None = Form(None),

    memory_limit_mb: int | None = Form(None),
    time_limit_sec: int | None = Form(None),

    visibility: bool | None = Form(None),
    source: str | None = Form(None),
    editorial: str | None = Form(None),

    tests_zip: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(oauth2.get_current_admin)
):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(detail="Problem with given ID was not found", status_code=status.HTTP_404_NOT_FOUND)

    if title is not None:
        problem.title = title
    if description is not None:
        problem.description = description
    if difficulty is not None:
        problem.difficulty = difficulty
    if input_desc is not None:
        problem.input_desc = input_desc
    if output_desc is not None:
        problem.output_desc = output_desc
    if explanation is not None:
        problem.explanation = explanation
    if memory_limit_mb is not None:
        problem.memory_limit_mb = memory_limit_mb
    if time_limit_sec is not None:
        problem.time_limit_sec = time_limit_sec
    if visibility is not None:
        problem.visibility = visibility
    if source is not None:
        problem.source = source
    if editorial is not None:
        problem.editorial = editorial

    if constraints is not None:
        try:
            problem.constraints = json.loads(constraints)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(detail="Invalid JSON for constraints", status_code=status.HTTP_400_BAD_REQUEST)

    if sample_io is not None:
        try:
            problem.sample_io = json.loads(sample_io)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(detail="Invalid JSON for sample_io", status_code=status.HTTP_400_BAD_REQUEST)

    if tags is not None:
        try:
            tag_slugs = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(detail="Invalid JSON for tags", status_code=status.HTTP_400_BAD_REQUEST)
        categories = db.query(Category).filter(Category.slug.in_(tag_slugs)).all()
        if len(categories) != len(tag_slugs):
            raise HTTPException(detail="One or more tags are invalid", status_code=status.HTTP_400_BAD_REQUEST)
        problem.tags = categories

    if tests_zip is not None and tests_zip.filename:
        if not tests_zip.filename.endswith(".zip"):
            raise HTTPException(detail="Only ZIP files are allowed", status_code=status.HTTP_400_BAD_REQUEST)

        zip_bytes = await tests_zip.read()
        try:
            zip_file = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            raise HTTPException(detail="Invalid ZIP file", status_code=status.HTTP_400_BAD_REQUEST)

        all_files = zip_file.namelist()
        prefix = tests_zip.filename.split(".")[0]

        input_files = sorted([
            f for f in all_files
            if f.startswith(prefix + "/inputs/") and not f.endswith("/")
        ])
        output_files = sorted([
            f for f in all_files
            if f.startswith(prefix + "/outputs/") and not f.endswith("/")
        ])

        if not input_files or not output_files:
            zip_file.close()
            raise HTTPException(detail="ZIP must contain inputs/ and outputs/", status_code=status.HTTP_400_BAD_REQUEST)
        if len(input_files) != len(output_files):
            zip_file.close()
            raise HTTPException(detail="Mismatch between input and output files", status_code=status.HTTP_400_BAD_REQUEST)

        for input_file, output_file in zip(input_files, output_files):
            if input_file.split("/")[-1] != output_file.split("/")[-1]:
                zip_file.close()
                raise HTTPException(detail="Mismatch in input and output file name", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            # Delete existing testcase files and database records
            get_storage_testcases().delete_problem_folder(problem.id)
            db.query(TestCase).filter(TestCase.problem_id == problem.id).delete()

            for input_path, output_path in zip(input_files, output_files):
                input_data = zip_file.read(input_path)
                output_data = zip_file.read(output_path)

                input_key = get_storage_testcases().upload_bytes(
                    problem_id=problem.id,
                    filename=input_path.split("/")[-1],
                    data=input_data
                )
                output_key = get_storage_testcases().upload_bytes(
                    problem_id=problem.id,
                    filename=output_path.split("/")[-1],
                    data=output_data
                )
                testcase = TestCase(
                    problem_id=problem.id,
                    input_key=input_key,
                    output_key=output_key
                )
                db.add(testcase)
        finally:
            zip_file.close()

    db.commit()
    db.refresh(problem)

    return {
        "id": problem.id,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "tags": [tag.slug for tag in problem.tags],
        "accepted_submissions": problem.accepted_submissions or 0,
        "total_submissions": problem.total_submissions or 0,

        "description": problem.description,
        "constraints": problem.constraints,
        "input_desc": problem.input_desc,
        "output_desc": problem.output_desc,
        "sample_io": problem.sample_io,
        "explanation": problem.explanation,

        "memory_limit_mb": problem.memory_limit_mb,
        "time_limit_sec": problem.time_limit_sec,

        "source": problem.source,
        "editorial": problem.editorial,
        "visibility": problem.visibility
    }

@router.delete('/', status_code=status.HTTP_204_NO_CONTENT)
def delete_problem(problem_id: str, current_user: User = Depends(oauth2.get_current_admin), db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(detail="Problem with given ID not found", status_code=status.HTTP_404_NOT_FOUND)
    
    submissions = db.query(Submission).filter(Submission.problem_id == problem.id).all()
    for submission in submissions:
        get_storage_submission_code().delete_file(submission.code_object_key)
    
    get_storage_testcases().delete_problem_folder(problem.id)
    
    db.delete(problem)
    db.commit()