import io
import tarfile
import docker
import socket
from docker.utils.socket import frames_iter

from config import (
    WORKSPACE_DIR,
)
from shared.models import Language, FILENAME, Verdict
from .types import CompileResult, RunResult

class JudgeExecutor:
    def __init__(self):
        self.workspace_dir = WORKSPACE_DIR
        self.client = docker.from_env()

    def _container_exec(self, container, cmd: list[str], workdir: str = WORKSPACE_DIR):
        return container.exec_run(cmd, workdir=workdir, tty=False, demux=True)
    
    def compile_c(self, container) -> CompileResult:
        cmd = [
            "/bin/sh",
            "-lc",
            f"timeout -s KILL 10s gcc -O2 -pipe -static -s -o {WORKSPACE_DIR}/main.out {WORKSPACE_DIR}/main.c 2>&1",
        ]
        result = self._container_exec(container, cmd)
        exit_code = int(result.exit_code)

        stdout_b, stderr_b = result.output if isinstance(result.output, tuple) else (b"", b"")
        out = (stdout_b or b"").decode(errors="replace") + (stderr_b or b"").decode(errors="replace")

        return CompileResult(
            ok=exit_code == 0,
            output=out,
            exit_code=exit_code,
        )

    def compile_cpp(self, container) -> CompileResult:
        cmd = [
            "/bin/sh",
            "-lc",
            f"timeout -s KILL 10s g++ -O2 -std=c++17 -pipe -static -s -o {WORKSPACE_DIR}/main.out {WORKSPACE_DIR}/main.cpp 2>&1",
        ]
        result = self._container_exec(container, cmd)
        exit_code = int(result.exit_code)

        stdout_b, stderr_b = result.output if isinstance(result.output, tuple) else (b"", b"")
        out = (stdout_b or b"").decode(errors="replace") + (stderr_b or b"").decode(errors="replace")

        return CompileResult(
            ok=exit_code == 0,
            output=out,
            exit_code=exit_code,
        )

    def compile_java(self, container) -> CompileResult:
        cmd = [
            "/bin/sh",
            "-lc",
            f"timeout -s KILL 10s javac -d {WORKSPACE_DIR} {WORKSPACE_DIR}/Main.java 2>&1",
        ]
        result = self._container_exec(container, cmd)
        exit_code = int(result.exit_code)

        stdout_b, stderr_b = result.output if isinstance(result.output, tuple) else (b"", b"")
        out = (stdout_b or b"").decode(errors="replace") + (stderr_b or b"").decode(errors="replace")

        return CompileResult(
            ok=exit_code == 0,
            output=out,
            exit_code=exit_code,
        )

    def run_program(
        self,
        container,
        language: Language,
        executable_path: str,
        input_data: str,
        expected_output: str,
        time_limit_sec: int,
        memory_limit_kb: int,
    ) -> RunResult:
        
        # Build command
        if language == Language.C:
            inner_cmd = f"{executable_path}"
        elif language == Language.CPP:
            inner_cmd = f"{executable_path}"
        elif language == Language.PYTHON:
            inner_cmd = f"python3 {executable_path}"
        elif language == Language.JAVA:
            inner_cmd = f"java -cp {self.workspace_dir} {executable_path}"
        else:
            raise ValueError(f"Unsupported language: {language}")


        cmd = [
            "/bin/sh",
            "-lc",
            f"/usr/bin/time -f \'%e %M\' timeout -s KILL {time_limit_sec}s sh -c \"{inner_cmd} 2>/dev/null\""
        ]

        exec_id = self.client.api.exec_create(
            container.id,
            cmd=cmd,
            # stdin=False,
            stdin=True,
            tty=False,
            user='run'
        )["Id"]

        sock = self.client.api.exec_start(
            exec_id,
            socket=True,
            tty=False,
        )

        # send stdin
        sock._sock.sendall(input_data.encode())
        try:
            sock._sock.shutdown(socket.SHUT_WR)
        except Exception:
            pass

        stdout_chunks = []
        stderr_chunks = []

        for stream_id, payload in frames_iter(socket=sock, tty=False):
            if stream_id == 1:
                stdout_chunks.append(payload)
            elif stream_id == 2:
                stderr_chunks.append(payload)

        sock.close()

        inspect = self.client.api.exec_inspect(exec_id)
        exit_code = inspect["ExitCode"]

        stdout_output = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr_output = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        stats = stderr_output.split("\n")[-2].split()

        time_elapsed = min(int(float(stats[0]) * 1000), time_limit_sec * 1000)
        memory_kb_used = min(int(stats[1]), memory_limit_kb)

        if memory_kb_used == memory_limit_kb:
            verdict = Verdict.MEMORY_LIMIT_EXCEEDED
        elif exit_code in (124, 137):
            verdict = Verdict.TIME_LIMIT_EXCEEDED
        elif exit_code != 0:
            verdict = Verdict.RUNTIME_ERROR
        else:
            # compare output
            def norm(s: str) -> str:
                return "\n".join(s.strip().split())            
            verdict = Verdict.ACCEPTED if norm(stdout_output) == norm(expected_output) else Verdict.WRONG_ANSWER

        return RunResult(
            ok=(verdict == Verdict.ACCEPTED),
            verdict=verdict,
            output=stdout_output,
            exit_code=exit_code,
            runtime_ms = time_elapsed,
            memory_kb = memory_kb_used
        )

    def copy_code_to_container(self, container, language: Language, code: bytes) -> None:
        tar_stream = io.BytesIO()

        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            file_data = io.BytesIO(code)

            tar_info = tarfile.TarInfo(name=FILENAME[language])
            tar_info.size = len(code)

            tar.addfile(tar_info, file_data)

        tar_stream.seek(0)

        container.put_archive(
            path=WORKSPACE_DIR,
            data=tar_stream.getvalue(),
        )