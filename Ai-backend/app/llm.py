from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .config import Settings
from .embeddings import strip_vietnamese_accents
from .models import SourceSnippet
from .qa_pairs import best_qa_match, is_question_like


class NarratorLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        question: str,
        snippets: list[SourceSnippet],
        persona: dict[str, str] | None = None,
    ) -> str:
        unsupported_claim = _unsupported_claim_answer(question, snippets)
        if unsupported_claim is not None:
            return _moderate_output(unsupported_claim)

        if _needs_explicit_policy_evidence(question) and not _has_explicit_policy_evidence(snippets):
            return _moderate_output(self._missing_policy_evidence_answer(snippets))

        if self.settings.llm_provider in {"fpt_cloud", "openai_compatible"} and self.settings.llm_api_key:
            try:
                return _moderate_output(self._generate_chat_completion(question, snippets, persona))
            except Exception as exc:
                local = self._generate_local(question, snippets)
                return _moderate_output(
                    f"{local}\n\n"
                    f"(Ghi chú kỹ thuật: LLM API chưa phản hồi thành công, hệ thống dùng bản local. Lỗi: {exc})"
                )

        return _moderate_output(self._generate_local(question, snippets))

    @staticmethod
    def _missing_policy_evidence_answer(snippets: list[SourceSnippet]) -> str:
        source = ""
        if snippets:
            source = f" Nguồn đã kiểm tra: {NarratorLLM._source_label(snippets[0])} - {snippets[0].title}."
        return (
            "Trong các tư liệu hiện có, mình chưa tìm thấy quy định trực tiếp về việc ai được phép "
            "hoặc không được phép thực hành nội dung này trong lễ hội. Tài liệu chỉ nói về cộng đồng "
            "chủ thể và việc tôn trọng bối cảnh di sản, nên mình không thể suy ra một điều cấm hay "
            "điều kiện bắt buộc."
            + source
        )

    def _generate_chat_completion(
        self,
        question: str,
        snippets: list[SourceSnippet],
        persona: dict[str, str] | None = None,
    ) -> str:
        url = self.settings.llm_api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
            "top_p": 1,
            "top_k": 40,
            "presence_penalty": 0,
            "frequency_penalty": 0,
            "stream": self.settings.llm_stream,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Không liệt kê các bước suy luận như 'Bước 1', 'Bước 2' hay 'Kết luận'. "
                        "Hãy trả lời trực tiếp, tự nhiên, giàu hình ảnh như một người dẫn chuyện về di sản; "
                        "nếu có nguồn phù hợp thì ghi nguồn ở cuối câu trả lời. "
                        "Với câu hỏi về ai được phép, ai không được phép, điều cấm, điều kiện bắt buộc hoặc quy định, "
                        "chỉ trả lời khi tư liệu nêu trực tiếp điều đó. Không được suy ra lệnh cấm từ địa phương, cộng đồng chủ thể, "
                        "việc tôn trọng bản sắc hay một thông tin gần nghĩa; nếu không có câu trả lời trực tiếp, hãy nói rõ tư liệu chưa nêu. "
                        "Khi chưa có thông tin, hãy nói mềm mại và hữu ích, bắt đầu bằng 'Dạ' nếu phù hợp; "
                        "nêu rõ kho tư liệu hiện tại chưa ghi nhận điều người dùng hỏi, sau đó chỉ gợi ý một di sản hoặc chủ đề gần đó "
                        "nếu các đoạn tư liệu được cung cấp có căn cứ. Tránh câu trả lời cụt như 'Tư liệu không đề cập'. "
                        "Luôn giữ thái độ lịch sự, điềm tĩnh và không công kích, xúc phạm, khiêu khích, phân biệt "
                        "hay quy chụp người dùng hoặc bất kỳ cộng đồng nào. "
                        "Bạn là Nghệ Nhân AI giới thiệu di sản cho du khách bằng tiếng Việt tự nhiên. "
                        "Chỉ sử dụng sự kiện có trong tư liệu được cung cấp; không tự bổ sung dữ kiện. "
                        "Trả lời ngắn gọn, mạch lạc, có chất kể chuyện nhưng vẫn đúng nguồn."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(question, snippets, persona),
                },
            ],
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ChatbotDeepSearch/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                response_body = response.read()
                response_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM không kết nối được: {exc.reason}") from exc

        return extract_chat_response_content(response_body, response_type)

    @staticmethod
    def _build_prompt(
        question: str,
        snippets: list[SourceSnippet],
        persona: dict[str, str] | None = None,
    ) -> str:
        persona_instruction = ""
        if persona:
            persona_details = "; ".join(f"{key}={value}" for key, value in persona.items())
            persona_instruction = (
                "\n\nPersona nghe nhan do client cung cap: "
                f"{persona_details}. Hay giu giong ke chuyen phu hop, "
                "nhung chi su dung cac su kien co trong tu lieu."
            )
        question = question + persona_instruction
        context = []
        for index, snippet in enumerate(snippets, start=1):
            page = f", trang {snippet.page}" if snippet.page else ""
            context.append(f"[S{index}] Nguồn: {snippet.title}{page}\n{snippet.text}")
        joined = "\n\n".join(context) if context else "Không có tư liệu liên quan."
        return (
            f"Câu hỏi của du khách: {question}\n\n"
            "Nếu tư liệu có phần 'Câu hỏi kiểm tra' và 'Đáp án', hãy ưu tiên cặp hỏi-đáp phù hợp nhất. "
            "Nếu người dùng chỉ nhập một chủ đề ngắn, hãy tóm tắt các tư liệu liên quan rõ ràng. "
            "Không bịa thêm dữ kiện ngoài tư liệu. Không viết các mục 'Bước 1', 'Bước 2' hay 'Kết luận'; "
            "hãy trả lời như một người thuyết minh đang dẫn du khách đi qua câu chuyện. "
            "Đặc biệt, không biến dữ kiện mô tả cộng đồng hoặc địa phương thành quy định được phép/không được phép nếu tài liệu không nói rõ.\n\n"
            f"Tư liệu truy xuất:\n{joined}"
        )

    def _generate_local(self, question: str, snippets: list[SourceSnippet]) -> str:
        if not snippets:
            return (
                "Dạ, trong kho tư liệu hiện tại mình chưa tìm thấy nội dung đủ gần để trả lời câu hỏi này một cách chắc chắn ạ. "
                "Bạn thử nêu rõ tên di sản, địa danh hoặc lễ hội; mình sẽ tìm lại trong các tài liệu đã được cung cấp nhé."
            )

        qa_match = best_qa_match(question, snippets)
        if qa_match is not None:
            source = self._source_label(qa_match.snippet)
            context_sentence = self._best_sentence(question, qa_match.snippet.text)
            return (
                "Dựa trên phần câu hỏi-đáp trong tài liệu, câu trả lời phù hợp nhất là: "
                f"{qa_match.pair.answer}. [{source}]\n\n"
                f"Phần nội dung liên quan trong tài liệu cũng cho biết: {context_sentence} [{source}]\n\n"
                f"Nguồn tham khảo: {source} - {qa_match.snippet.title}."
            )

        if not is_question_like(question):
            return self._generate_topic_overview(question, snippets)

        lead = (
            "Hãy hình dung ta đang đứng trong một gian trưng bày yên tĩnh. "
            f"Với câu hỏi “{question}”, các tư liệu gần nhất gợi ra như sau: "
        )
        facts: list[str] = []
        for snippet in snippets[:3]:
            sentence = self._best_sentence(question, snippet.text)
            source = self._source_label(snippet)
            facts.append(f"{sentence} [{source}]")

        source_list = "; ".join(
            self._source_label(snippet) + f" - {snippet.title}" for snippet in snippets[:5]
        )
        return lead + " ".join(facts) + f"\n\nNguồn tham khảo: {source_list}."

    def _generate_topic_overview(self, topic: str, snippets: list[SourceSnippet]) -> str:
        intro = f"Trong các PDF, mình tìm thấy một số nội dung liên quan đến “{topic}”:"
        lines: list[str] = []
        for snippet in snippets[:4]:
            source = self._source_label(snippet)
            summary = self._best_sentence(topic, self._remove_qa_section(snippet.text))
            if not summary:
                summary = self._best_sentence(topic, snippet.text)
            lines.append(f"- {summary} [{source}]")

        source_list = "; ".join(
            self._source_label(snippet) + f" - {snippet.title}" for snippet in snippets[:4]
        )
        return (
            intro
            + "\n"
            + "\n".join(lines)
            + f"\n\nTóm lại, “{topic}” đang xuất hiện trong các tài liệu trên như một chủ đề di sản "
            "hoặc địa danh gắn với các thực hành văn hóa cụ thể."
            + f"\n\nNguồn tham khảo: {source_list}."
        )

    @staticmethod
    def _best_sentence(question: str, text: str) -> str:
        pieces = re.split(r"(?<=[.!?。])\s+", text.strip())
        if not pieces:
            return text.strip()[:420].rstrip()

        question_terms = set(re.findall(r"[\wÀ-ỹ]+", question.lower(), re.UNICODE))
        best = max(
            pieces,
            key=lambda sentence: len(
                question_terms.intersection(re.findall(r"[\wÀ-ỹ]+", sentence.lower(), re.UNICODE))
            ),
        )
        sentence = best or pieces[0]
        return sentence[:420].rstrip()

    @staticmethod
    def _remove_qa_section(text: str) -> str:
        return re.split(r"CÂU HỎI|Câu\s+\d+\.|Cau\s+\d+\.", text, maxsplit=1)[0].strip()

    @staticmethod
    def _source_label(snippet: SourceSnippet) -> str:
        page = f", tr. {snippet.page}" if snippet.page else ""
        return f"{snippet.source}{page}"


def extract_chat_response_content(response_body: bytes, response_type: str = "") -> str:
    decoded = response_body.decode("utf-8", errors="replace").strip()
    if not decoded:
        raise RuntimeError("LLM khong tra ve noi dung.")

    if _looks_like_sse(decoded, response_type):
        return _extract_streamed_chat_content(decoded)

    try:
        body = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM tra ve response khong phai JSON: {decoded[:500]}") from exc

    return _extract_chat_content(body)


def _needs_explicit_policy_evidence(question: str) -> bool:
    tokens = re.findall(r"[\w]+", strip_vietnamese_accents(question.lower()), re.UNICODE)
    phrases = {
        ("khong", "duoc", "phep"),
        ("duoc", "phep"),
        ("cam",),
        ("bat", "buoc"),
        ("dieu", "kien"),
        ("ai", "duoc"),
        ("ai", "khong"),
    }
    return any(_contains_token_phrase(tokens, phrase) for phrase in phrases)


def _unsupported_claim_answer(question: str, snippets: list[SourceSnippet]) -> str | None:
    plain = strip_vietnamese_accents(question.lower())
    marker = "ghi rang"
    if marker not in plain:
        return None

    claim = plain.split(marker, 1)[1]
    claim_tokens = [token for token in re.findall(r"[\w]+", claim) if len(token) > 2]
    if len(claim_tokens) < 4:
        return None

    context = strip_vietnamese_accents(" ".join(snippet.text.lower() for snippet in snippets))
    claim_bigrams = list(zip(claim_tokens, claim_tokens[1:]))
    supported_bigrams = sum(
        1 for left, right in claim_bigrams if f"{left} {right}" in context
    )
    if supported_bigrams >= max(1, len(claim_bigrams) // 4):
        return None

    source_lines = ""
    if snippets:
        labels = "; ".join(f"{snippet.source}, tr. {snippet.page}" for snippet in snippets[:2])
        source_lines = f" Nguồn đã đối chiếu: {labels}."
    return (
        "Dạ, mình chưa tìm thấy đoạn tư liệu nào xác nhận mối liên hệ được nêu trong câu hỏi ạ. "
        "Có thể câu hỏi đang ghép hai phần thông tin của Đờn ca tài tử Nam Bộ và Không gian văn hóa "
        "Cồng chiêng Tây Nguyên; vì vậy mình không nên suy ra rằng các nhạc cụ của di sản này được "
        "dùng thay cho di sản kia để xua đuổi tà ma hay gọi mưa."
        + source_lines
    )


def _contains_token_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    width = len(phrase)
    return any(tuple(tokens[index : index + width]) == phrase for index in range(len(tokens) - width + 1))


def _moderate_output(answer: str) -> str:
    plain = strip_vietnamese_accents(answer.lower())
    hostile_patterns = (
        r"\bngu(?:oi)?\s+(dung|dốt)\b",
        r"\bdo\s+\w+\s+(ngu|dien|vo dung)\b",
        r"\b(câm|cam)\s+di\b",
        r"\b(im|bien)\s+di\b",
        r"\bmat\s+day\b",
        r"\bvo\s+dung\b",
        r"\bkhong\s+xung\s+dang\b",
        r"\b(lu|bon)\s+\w+\b",
    )
    if any(re.search(pattern, plain) for pattern in hostile_patterns):
        return (
            "Dạ, mình xin giữ cuộc trò chuyện ở tinh thần tôn trọng và xây dựng ạ. "
            "Mình có thể giúp bạn tìm hiểu lịch sử, văn hóa và các di sản trong kho tư liệu."
        )
    return answer


def _has_explicit_policy_evidence(snippets: list[SourceSnippet]) -> bool:
    combined = " ".join(snippet.text.lower() for snippet in snippets)
    return any(
        phrase in combined
        for phrase in (
            "không được phép",
            "khong duoc phep",
            "được phép",
            "duoc phep",
            "cấm",
            "cam ",
            "bắt buộc",
            "bat buoc",
            "điều kiện",
            "dieu kien",
        )
    )


def _looks_like_sse(decoded: str, response_type: str) -> bool:
    if "text/event-stream" in response_type.lower():
        return True
    return any(line.lstrip().startswith("data:") for line in decoded.splitlines())


def _extract_streamed_chat_content(decoded: str) -> str:
    pieces: list[str] = []
    events_seen = 0

    for raw_line in decoded.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue

        events_seen += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(event, dict):
            continue

        error = event.get("error")
        if error:
            raise RuntimeError(f"LLM stream tra ve loi: {error}")

        data = event.get("data")
        payload = data if isinstance(data, dict) else event

        choices = payload.get("choices") or []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            pieces.extend(_iter_choice_text_values(choice))

    content = "".join(pieces).strip()
    if content:
        return content
    raise RuntimeError(f"LLM stream khong tra ve noi dung qua {events_seen} event.")


def _iter_choice_text_values(choice: dict):
    delta = choice.get("delta") or {}
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            yield content

    message = choice.get("message") or {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            yield content

    text = choice.get("text")
    if isinstance(text, str):
        yield text


def _extract_chat_content(body: dict) -> str:
    payload = body.get("data") if isinstance(body.get("data"), dict) else body
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM không trả về choices: {body}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    text = choices[0].get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    raise RuntimeError(f"LLM không trả về nội dung: {body}")
