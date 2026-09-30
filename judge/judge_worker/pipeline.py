import docker
from contextlib import contextmanager

from shared.models import Submission, TestCase, Language, Verdict, Problem
from config import (
    ACQUIRE_TIMEOUT_SECONDS,
    WORKSPACE_DIR,
)
from .types import SubmissionResult

class JudgePipeline:
    def __init__(self, db, storage, queues, executor):
        self.db = db
        self.storage = storage
        self.queues = queues
        self.executor = executor
        self.client = docker.from_env()
    
    @contextmanager
    def _get_container(self, container_id: str):
        try:
            container = self.client.containers.get(container_id)
        except Exception as e:
            raise RuntimeError(f"get container failed for container id: {container_id}")

        try:
            yield container
        finally:
            container.stop(timeout=0)    

    def _get_submission(self, db, submission_id: int):
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")
        return submission

    def _get_testcases(self, db, problem_id: str):
        testcases = db.query(TestCase).filter(TestCase.problem_id == problem_id).order_by(TestCase.id).all()
        if testcases is None:
            raise ValueError(f"Testcases for problem {problem_id} not found")
        return testcases
    
    def _get_time_mem_limit(self, db, problem_id: str):
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        if problem is None:
            raise ValueError(f"Problem {problem_id} not found")
        time_limit_sec = problem.time_limit_sec
        memory_limit_kb = problem.memory_limit_mb * 1024
        return time_limit_sec, memory_limit_kb

    def _update_submission_result(self, submission_id: int, result: SubmissionResult) -> None:
        with self.db.session() as db:
            submission = db.query(Submission).filter(Submission.id == submission_id).first()
            if submission is None:
                return
            
            submission.verdict = result.verdict
            submission.output = result.output
            submission.incorrect_testcase_key = result.incorrect_testcase_key
            submission.walltime_ms = result.runtime_ms
            submission.memory_kb = result.memory_kb

            problem = db.query(Problem).filter(Problem.id == submission.problem_id).first()
            if problem is not None:
                problem.total_submissions = (problem.total_submissions or 0) + 1
                if result.verdict == Verdict.ACCEPTED:
                    problem.accepted_submissions = (problem.accepted_submissions or 0) + 1


    def process_submission(self, submission_id: int) -> SubmissionResult:

        with self.db.session() as db:
            submission = self._get_submission(db, submission_id)
            problem_id = submission.problem_id
            language = submission.language.value
            testcases = self._get_testcases(db, problem_id)
            time_limit_sec, memory_limit_kb = self._get_time_mem_limit(db, problem_id)

        container_id = self.queues.acquire_warm_sandbox(language, timeout=ACQUIRE_TIMEOUT_SECONDS)
        if container_id is None:
            raise TimeoutError(f"No warm sandbox available for {language}")
        
        self.queues.publish_event({
            "submission_id": submission_id,
            "language": language,
        })

        container = None
        result = SubmissionResult(submission_id=submission_id, verdict=Verdict.PENDING)

        with self._get_container(container_id) as container:
            
            code_data = self.storage.read_submission_code(submission.code_object_key)
            self.executor.copy_code_to_container(container, language, code_data)

            if language == Language.C:
                compile_result = self.executor.compile_c(container)
                if not compile_result.ok:
                    result.verdict = Verdict.COMPILATION_ERROR
                    result.output = compile_result.output
                executable_path = f"{WORKSPACE_DIR}/main.out"

            elif language == Language.CPP:
                compile_result = self.executor.compile_cpp(container)
                if not compile_result.ok:
                    result.verdict = Verdict.COMPILATION_ERROR
                    result.output = compile_result.output
                executable_path = f"{WORKSPACE_DIR}/main.out"

            elif language == Language.PYTHON:
                executable_path = f"{WORKSPACE_DIR}/main.py"

            elif language == Language.JAVA:
                compile_result = self.executor.compile_java(container)
                if not compile_result.ok:
                    result.verdict = Verdict.COMPILATION_ERROR
                    result.output = compile_result.output
                executable_path = "Main"
            else:
                raise ValueError(f"Unsupported language: {language}")

            
            if result.verdict == Verdict.PENDING:
                final_verdict = Verdict.ACCEPTED
                first_failure = None
                max_runtime_ms = 0
                max_memory_used_kb = 0

                for idx, testcase in enumerate(testcases, start=1):
                    input_data = self.storage.read_testcase_input(testcase.input_key).decode("utf-8")
                    expected_output = self.storage.read_testcase_output(testcase.output_key).decode("utf-8")

                    run_result = self.executor.run_program(
                        container=container,
                        language=language,
                        executable_path=executable_path,
                        input_data=input_data,
                        expected_output=expected_output,
                        time_limit_sec=time_limit_sec,
                        memory_limit_kb=memory_limit_kb
                    )

                    max_runtime_ms = max(max_runtime_ms, run_result.runtime_ms)
                    max_memory_used_kb = max(max_memory_used_kb, run_result.memory_kb)

                    if not run_result.ok:
                        final_verdict = run_result.verdict
                        first_failure = {
                            "incorrect_testcase_idx": idx,
                            "incorrect_testcase_key": testcase.input_key,
                            "output": run_result.output[:8192],
                        }
                        break

                result.verdict = final_verdict
                result.runtime_ms = max_runtime_ms
                result.memory_kb = max_memory_used_kb
                
                if result.verdict != Verdict.ACCEPTED:
                    result.incorrect_testcase_idx = first_failure["incorrect_testcase_idx"]
                    result.incorrect_testcase_key = first_failure["incorrect_testcase_key"]
                    result.output = first_failure["output"]

        self._update_submission_result(submission_id, result)

        return result
