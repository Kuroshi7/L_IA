"""Callback que loga cada etapa do agent: chamadas ao LLM, tools chamadas, durações."""

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

log = logging.getLogger("agent")


def _truncate(s: str, n: int = 200) -> str:
    s = str(s).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


class LiaTimingCallback(BaseCallbackHandler):
    """Imprime uma linha por evento (LLM start/end, tool start/end/error) com
    tempo relativo ao início da request e duração de cada chamada."""

    def __init__(self, session_id: str = "") -> None:
        self.session_id = session_id
        self.t0 = time.perf_counter()
        self.llm_calls = 0
        self._llm_starts: dict[UUID, tuple[float, int]] = {}
        self._tool_starts: dict[UUID, tuple[float, str]] = {}

    def _t(self) -> str:
        return f"+{time.perf_counter() - self.t0:6.2f}s"

    # ---- LLM ----
    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, **kwargs: Any) -> None:
        self.llm_calls += 1
        # `messages` é list[list[BaseMessage]] — pegamos a 1ª batch
        batch = messages[0] if messages else []
        n_chars = sum(len(getattr(m, "content", "") or "") for m in batch)
        n_msgs = len(batch)
        self._llm_starts[run_id] = (time.perf_counter(), self.llm_calls)
        log.info(f"{self._t()} | LLM #{self.llm_calls} START   | msgs={n_msgs} | chars_in={n_chars}")

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        start, idx = self._llm_starts.pop(run_id, (time.perf_counter(), self.llm_calls))
        dur = time.perf_counter() - start

        tool_calls: list[str] = []
        content = ""
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            if msg is not None:
                tcs = getattr(msg, "tool_calls", None) or []
                for tc in tcs:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
                    tool_calls.append(f"{name}({_truncate(args, 100) if args else ''})")
                content = getattr(msg, "content", "") or ""
        except Exception as e:
            log.debug(f"falha ao parsear LLM response: {e}")

        log.info(
            f"{self._t()} | LLM #{idx} END     | dur={dur:5.2f}s | "
            f"out_chars={len(content)} | tools={tool_calls or '[]'}"
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        start, idx = self._llm_starts.pop(run_id, (time.perf_counter(), self.llm_calls))
        dur = time.perf_counter() - start
        log.error(f"{self._t()} | LLM #{idx} ERROR   | dur={dur:5.2f}s | {type(error).__name__}: {error}")

    # ---- Tools ----
    def on_tool_start(self, serialized, input_str, *, run_id: UUID, **kwargs: Any) -> None:
        name = (serialized or {}).get("name", "?")
        self._tool_starts[run_id] = (time.perf_counter(), name)
        log.info(f"{self._t()} | TOOL START      | name={name} | args={_truncate(input_str, 200)}")

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        start, name = self._tool_starts.pop(run_id, (time.perf_counter(), "?"))
        dur = time.perf_counter() - start
        out_str = _truncate(output, 300)
        log.info(f"{self._t()} | TOOL END        | name={name} | dur={dur:5.2f}s | result={out_str}")

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        start, name = self._tool_starts.pop(run_id, (time.perf_counter(), "?"))
        dur = time.perf_counter() - start
        log.error(
            f"{self._t()} | TOOL ERROR      | name={name} | dur={dur:5.2f}s | "
            f"{type(error).__name__}: {error}"
        )

    # ---- Chain (agent loop) ----
    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        log.error(f"{self._t()} | CHAIN ERROR     | {type(error).__name__}: {error}")
