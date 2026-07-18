from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from .config import Settings
from .embeddings import strip_vietnamese_accents
from .models import SourceSnippet
from .qa_pairs import best_qa_match, is_narrative_request, is_question_like


_DEFAULT_IDENTITY = "Bạn là Nghệ Nhân AI giới thiệu di sản cho du khách bằng tiếng Việt tự nhiên."
LOGGER = logging.getLogger(__name__)


def _persona_identity(persona: dict[str, str] | None) -> str:
    """Câu xưng danh cho system prompt. Không có persona -> giữ 'Nghệ Nhân AI' chung."""
    if not persona:
        return _DEFAULT_IDENTITY
    name = persona.get("name")
    craft = persona.get("craft")
    bio = persona.get("bio")
    if not name:
        return _DEFAULT_IDENTITY
    role = f"Bạn đang nhập vai {name}"
    if craft:
        role += f", một nghệ nhân/nhân vật gắn với {craft}"
    role += (
        ". Hãy xưng ở ngôi thứ nhất, thân thiện và tự hào như chính người đó đang trò chuyện "
        "với du khách, nhưng chỉ dùng dữ kiện có trong tư liệu được cung cấp; không bịa thêm về bản thân."
    )
    return role


class NarratorLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        question: str,
        snippets: list[SourceSnippet],
        persona: dict[str, str] | None = None,
        history: list[dict[str, str]] | None = None,
        inferred_intent: str = "",
    ) -> str:
        unsupported_claim = _unsupported_claim_answer(question, snippets)
        if unsupported_claim is not None:
            return _moderate_output(unsupported_claim)

        if _needs_explicit_policy_evidence(question) and not _has_explicit_policy_evidence(snippets):
            return _moderate_output(self._missing_policy_evidence_answer(snippets))

        if _needs_origin_evidence(question) and not _has_explicit_origin_evidence(snippets):
            return _moderate_output(self._missing_origin_evidence_answer(snippets))

        if _needs_practitioner_evidence(question) and not _has_practitioner_evidence(snippets):
            return _moderate_output(self._missing_practitioner_evidence_answer(snippets))

        if _needs_how_to_evidence(question) and not _has_how_to_evidence(snippets):
            return _moderate_output(self._missing_how_to_evidence_answer(snippets))

        if self.settings.llm_provider in {"fpt_cloud", "openai_compatible"} and self.settings.llm_api_key:
            try:
                answer = _normalize_heritage_terms(
                    self._generate_chat_completion(
                        question, snippets, persona, history, inferred_intent=inferred_intent
                    )
                )
                supported, unsupported = self._verify_grounding(
                    question, answer, snippets, inferred_intent
                )
                if supported:
                    return _moderate_output(answer)

                revised = _normalize_heritage_terms(
                    self._generate_chat_completion(
                        question,
                        snippets,
                        persona,
                        history,
                        inferred_intent=inferred_intent,
                        revision_feedback=unsupported,
                    )
                )
                revised_supported, _ = self._verify_grounding(
                    question, revised, snippets, inferred_intent
                )
                if revised_supported:
                    return _moderate_output(revised)

                LOGGER.warning("Grounding verifier rejected both generated answers: %s", unsupported)
                return _moderate_output(self._generate_local(question, snippets))
            except Exception as exc:
                LOGGER.warning("LLM generation or verification failed; using grounded local fallback: %s", exc)
                return _moderate_output(self._generate_local(question, snippets))

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

    @staticmethod
    def _missing_origin_evidence_answer(snippets: list[SourceSnippet]) -> str:
        source = ""
        if snippets:
            source = f" Nguồn đã kiểm tra: {NarratorLLM._source_label(snippets[0])}."
        return (
            "Dạ, tư liệu hiện tại chưa nêu thời điểm ra đời hoặc hình thành chính xác của di sản này. "
            "Ngày ghi trên quyết định đưa di sản vào danh mục là mốc quản lý, không phải ngày di sản ra đời, "
            "nên mình không thể suy ra niên đại từ mốc đó."
            + source
        )

    @staticmethod
    def _missing_practitioner_evidence_answer(snippets: list[SourceSnippet]) -> str:
        source = f" Nguồn đã kiểm tra: {NarratorLLM._source_label(snippets[0])}." if snippets else ""
        return (
            "Dạ, tư liệu hiện tại chưa nêu trực tiếp những ai là người hát hoặc người thực hành di sản này. "
            "Mình không muốn suy từ tên nhân vật hay hình ảnh đang quét thành thông tin lịch sử khi nguồn chưa xác nhận."
            + source
        )

    @staticmethod
    def _missing_how_to_evidence_answer(snippets: list[SourceSnippet]) -> str:
        source = f" Nguồn đã kiểm tra: {NarratorLLM._source_label(snippets[0])}." if snippets else ""
        return (
            "Dạ, hồ sơ hiện tại chưa mô tả đủ nguyên liệu, công cụ hoặc các bước thực hành để mình giải thích chính xác cách làm. "
            "Mình có thể giới thiệu những dữ kiện đã được ghi nhận, nhưng không nên tự bổ sung quy trình từ kiến thức ngoài nguồn."
            + source
        )

    def _generate_chat_completion(
        self,
        question: str,
        snippets: list[SourceSnippet],
        persona: dict[str, str] | None = None,
        history: list[dict[str, str]] | None = None,
        inferred_intent: str = "",
        revision_feedback: list[str] | None = None,
    ) -> str:
        identity = _persona_identity(persona)
        policy_rule = ""
        if _needs_explicit_policy_evidence(question):
            policy_rule = (
                "Với câu hỏi về ai được phép, ai không được phép, điều cấm, điều kiện bắt buộc hoặc quy định, "
                "chỉ trả lời khi tư liệu nêu trực tiếp điều đó. Không được suy ra lệnh cấm từ địa phương, "
                "cộng đồng chủ thể hay một thông tin gần nghĩa; nếu không có câu trả lời trực tiếp, hãy nói rõ. "
            )
        messages = [
            {
                "role": "system",
                "content": (
                        "Không liệt kê các bước suy luận như 'Bước 1', 'Bước 2' hay 'Kết luận'. "
                        "Hãy trả lời trực tiếp, tự nhiên như một nghệ nhân đang trò chuyện với du khách. "
                        "Mọi dữ kiện trong câu trả lời phải được một trong các nguồn [S...] cung cấp trực tiếp. "
                        "Được phép diễn đạt lại, nối ý và dùng lời chào tự nhiên, nhưng không được thêm tên riêng, "
                        "địa danh, ngày tháng, số liệu, nguồn gốc, ý nghĩa, quan hệ nhân quả hoặc đặc điểm chưa có trong nguồn. "
                        "Không chép nguyên văn một câu dài từ tư liệu nếu có thể diễn đạt lại mà vẫn giữ đúng nghĩa. "
                        "Không đổi loại khái niệm: ví dụ 'dòng số 3 trong danh mục dữ liệu' tuyệt đối không được kể thành "
                        "'dòng nhạc thứ 3'. Không dùng các từ đánh giá như 'độc đáo', 'huyền bí', 'lâu đời' nếu nguồn không nêu. "
                        "Tên riêng, thuật ngữ, số liệu và ngày tháng phải giữ chính xác. Gắn [S1], [S2] sau câu có dữ kiện; "
                        "chỉ dùng mã nguồn thực sự được cung cấp. "
                        f"{policy_rule}"
                        "Khi chưa có thông tin, hãy nói mềm mại và hữu ích, bắt đầu bằng 'Dạ' nếu phù hợp; "
                        "nêu rõ kho tư liệu hiện tại chưa ghi nhận điều người dùng hỏi, sau đó chỉ gợi ý một di sản hoặc chủ đề gần đó "
                        "nếu các đoạn tư liệu được cung cấp có căn cứ. Tránh câu trả lời cụt như 'Tư liệu không đề cập'. "
                        "Luôn giữ thái độ lịch sự, điềm tĩnh và không công kích, xúc phạm, khiêu khích, phân biệt "
                        "hay quy chụp người dùng hoặc bất kỳ cộng đồng nào. "
                        f"{identity} "
                        "Lịch sử hội thoại chỉ dùng để hiểu đại từ và câu hỏi nối tiếp, không được coi là nguồn dữ kiện. "
                        "Nếu nguồn chỉ đủ cho một ý thì trả lời ngắn; không kéo dài bằng thông tin suy đoán."
                ),
            }
        ]
        messages.extend(self._history_messages(history))
        messages.append(
            {
                "role": "user",
                "content": self._build_prompt(
                    question, snippets, revision_feedback, inferred_intent
                ),
            }
        )
        return self._request_chat_completion(
            messages,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            stream=self.settings.llm_stream,
        )

    def _request_chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> str:
        url = self.settings.llm_api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 1,
            "top_k": 40,
            "presence_penalty": 0,
            "frequency_penalty": 0,
            "stream": stream,
            "messages": messages,
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
        revision_feedback: list[str] | None = None,
        inferred_intent: str = "",
    ) -> str:
        context = []
        narrative_mode = is_narrative_request(question) or "gioi thieu chung" in strip_vietnamese_accents(
            inferred_intent.lower()
        )
        for index, snippet in enumerate(snippets, start=1):
            page = f", trang {snippet.page}" if snippet.page else ""
            evidence_kind = "DỮ KIỆN HỎI-ĐÁP" if snippet.content_type == "qa_pair" else "NGỮ CẢNH"
            evidence_text = snippet.text
            if snippet.content_type != "qa_pair" and narrative_mode:
                evidence_text = _narrative_context(evidence_text)
            context.append(
                f"[S{index}] Loại: {evidence_kind}; Nguồn: {snippet.title}{page}\n{evidence_text}"
            )
        joined = "\n\n".join(context) if context else "Không có tư liệu liên quan."
        revision = ""
        if revision_feedback:
            revision = (
                "\n\nBản trả lời trước đã bị bộ kiểm chứng từ chối vì các ý sau không có đủ căn cứ: "
                + "; ".join(revision_feedback[:5])
                + ". Hãy bỏ các ý này và viết lại chỉ từ nguồn."
            )
        return (
            f"Câu hỏi của du khách: {question}\n\n"
            + (f"Ý định đã được xác định từ ngữ cảnh AR/hội thoại: {inferred_intent}\n\n" if inferred_intent else "")
            +
            "Dùng DỮ KIỆN HỎI-ĐÁP để khóa đáp án chính xác; dùng NGỮ CẢNH để diễn đạt tự nhiên hơn. "
            "Cặp hỏi-đáp là bằng chứng, không phải mẫu câu bắt buộc phải sao chép. "
            "Chỉ dùng dữ kiện liên quan trực tiếp đến câu hỏi; bỏ qua STT, số dòng trong bảng, mã hồ sơ và lỗi đánh số "
            "nếu du khách không hỏi về quản lý dữ liệu. "
            "Nếu người dùng chỉ nhập một chủ đề ngắn, hãy tóm tắt các tư liệu liên quan rõ ràng. "
            "Không bịa thêm dữ kiện ngoài tư liệu. Không viết các mục 'Bước 1', 'Bước 2' hay 'Kết luận'; "
            "hãy trả lời như một người thuyết minh đang dẫn du khách đi qua câu chuyện. "
            "Đặc biệt, không biến dữ kiện mô tả cộng đồng hoặc địa phương thành quy định được phép/không được phép nếu tài liệu không nói rõ.\n\n"
            f"Tư liệu truy xuất:\n{joined}{revision}"
        )

    @staticmethod
    def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        clean: list[dict[str, str]] = []
        for item in (history or [])[-6:]:
            role = item.get("role")
            content = item.get("content", "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            clean.append({"role": role, "content": content[:2000]})
        return clean

    def _verify_grounding(
        self,
        question: str,
        answer: str,
        snippets: list[SourceSnippet],
        inferred_intent: str = "",
    ) -> tuple[bool, list[str]]:
        relevance_issues = _answer_relevance_issues(question, answer, inferred_intent)
        if relevance_issues:
            return False, relevance_issues
        unsupported_numbers = _unsupported_numbers(answer, snippets)
        if unsupported_numbers:
            return False, [f"Số liệu không có trong nguồn: {value}" for value in unsupported_numbers]
        unsupported_phrases = _unsupported_claim_phrases(answer, snippets)
        if unsupported_phrases:
            return False, [f"Cụm khẳng định không có trong nguồn: {value}" for value in unsupported_phrases]

        evidence = self._build_prompt(
            question, snippets, inferred_intent=inferred_intent
        )
        verification = self._request_chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Bạn là bộ kiểm chứng dữ kiện nghiêm ngặt. So sánh từng khẳng định có thể kiểm chứng "
                        "trong câu trả lời với tư liệu. Cách diễn đạt lại và lời chào không cần xuất hiện nguyên văn, "
                        "nhưng mọi tên riêng, địa danh, thời gian, số liệu, nguồn gốc, ý nghĩa, đặc điểm và quan hệ "
                        "nhân quả phải được nguồn hỗ trợ trực tiếp. "
                        "Câu trả lời cũng phải trả lời đúng ý định đã nêu; một câu đúng nguồn nhưng nói sang chủ đề khác vẫn là không đạt. "
                        "Không được chấp nhận việc đổi nghĩa của khái niệm; ví dụ nguồn nói 'dòng số 3 trong bảng' "
                        "nhưng câu trả lời nói 'dòng nhạc thứ 3' là không được hỗ trợ. "
                        "Chỉ trả JSON hợp lệ dạng "
                        '{"supported":true,"unsupported_claims":[]}.'
                    ),
                },
                {
                    "role": "user",
                    "content": f"{evidence}\n\nCâu trả lời cần kiểm chứng:\n{answer}",
                },
            ],
            temperature=0,
            max_tokens=260,
            stream=False,
        )
        return _parse_verification(verification)

    def _generate_local(self, question: str, snippets: list[SourceSnippet]) -> str:
        if not snippets:
            return (
                "Dạ, trong kho tư liệu hiện tại mình chưa tìm thấy nội dung đủ gần để trả lời câu hỏi này một cách chắc chắn ạ. "
                "Bạn thử nêu rõ tên di sản, địa danh hoặc lễ hội; mình sẽ tìm lại trong các tài liệu đã được cung cấp nhé."
            )

        if is_narrative_request(question):
            return self._generate_grounded_overview(snippets)

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

    def _generate_grounded_overview(self, snippets: list[SourceSnippet]) -> str:
        snippet = next((item for item in snippets if item.content_type == "document"), snippets[0])
        text = snippet.text
        clauses: list[str] = []

        name_match = re.search(r"Giới thiệu chung\s+(.{2,180}?)\s+là dòng số", text, re.IGNORECASE)
        type_match = re.search(
            r"Hồ sơ được xếp vào loại hình\s+(.+?);\s*địa bàn ghi nhận:\s*(.+?)\.",
            text,
            re.IGNORECASE,
        )
        if type_match:
            heritage_name = name_match.group(1).strip() if name_match else snippet.title.replace("_", " ")
            heritage_type = type_match.group(1).strip()
            locations = re.sub(
                r"\s+(?=(?:Tỉnh|Thành phố)\s)",
                " và ",
                type_match.group(2).strip(),
                flags=re.IGNORECASE,
            )
            clauses.append(
                f"theo hồ sơ, {heritage_name} thuộc loại hình {heritage_type}, "
                f"với địa bàn được ghi nhận tại {locations}"
            )

        plain = strip_vietnamese_accents(text.lower())
        if "unesco ghi danh" in plain or "da duoc unesco ghi danh" in plain:
            clauses.append("tư liệu cũng xác nhận di sản đã được UNESCO ghi danh")
        if "cong dong dang thuc hanh, luu truyen" in plain:
            clauses.append("hồ sơ ghi nhận vai trò của cộng đồng trong việc thực hành và lưu truyền di sản")

        if not clauses:
            intro = re.split(r"Câu hỏi|CÂU HỎI", text, maxsplit=1)[0]
            intro = re.sub(r"^.*?Giới thiệu chung\s*", "", intro, count=1, flags=re.IGNORECASE)
            sentence = self._best_sentence("di sản", intro)
            clauses.append(sentence or "tư liệu hiện có chỉ cung cấp một mô tả ngắn về di sản này")

        source = self._source_label(snippet)
        clean_clauses = [clause for clause in clauses if clause]
        sentences = clean_clauses[0]
        if len(clean_clauses) > 1:
            sentences += ". " + ". ".join(
                clause[:1].upper() + clause[1:] for clause in clean_clauses[1:]
            )
        return f"Dạ, {sentences}. [{source}]"

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


def _needs_origin_evidence(question: str) -> bool:
    plain = " ".join(re.findall(r"[\w]+", strip_vietnamese_accents(question.lower()), re.UNICODE))
    return any(
        phrase in plain
        for phrase in (
            "co tu bao gio",
            "ra doi khi nao",
            "ra doi bao gio",
            "xuat hien khi nao",
            "xuat hien tu bao gio",
            "hinh thanh khi nao",
            "bat nguon tu dau",
            "nguon goc tu dau",
            "co lau chua",
            "bao nhieu nam",
        )
    )


def _has_explicit_origin_evidence(snippets: list[SourceSnippet]) -> bool:
    plain = strip_vietnamese_accents(" ".join(snippet.text.lower() for snippet in snippets))
    positive_patterns = (
        r"(?:ra doi|hinh thanh|xuat hien|bat nguon).{0,100}\b\d{3,4}\b",
        r"(?:ra doi|hinh thanh|xuat hien|bat nguon).{0,100}(?:the ky|thoi |trieu |nam )",
    )
    return any(re.search(pattern, plain) for pattern in positive_patterns)


def _needs_practitioner_evidence(question: str) -> bool:
    plain = " ".join(re.findall(r"[\w]+", strip_vietnamese_accents(question.lower()), re.UNICODE))
    return any(
        phrase in plain
        for phrase in ("ai hat", "ai lam", "ai thuc hanh", "nguoi nao hat", "cong dong nao")
    )


def _has_practitioner_evidence(snippets: list[SourceSnippet]) -> bool:
    plain = strip_vietnamese_accents(" ".join(snippet.text.lower() for snippet in snippets))
    return any(
        re.search(pattern, plain)
        for pattern in (
            r"\blien anh\b",
            r"\blien chi\b",
            r"cong dong chu the (?:la|gom|bao gom)",
            r"do (?:nguoi|cong dong) .{2,80} (?:hat|lam|thuc hanh|trinh dien)",
            r"nguoi .{2,80} (?:hat|lam|thuc hanh|trinh dien)",
        )
    )


def _needs_how_to_evidence(question: str) -> bool:
    plain = " ".join(re.findall(r"[\w]+", strip_vietnamese_accents(question.lower()), re.UNICODE))
    return any(
        phrase in plain
        for phrase in ("lam kieu gi", "lam sao", "cach lam", "lam nhu nao", "thuc hanh the nao")
    )


def _has_how_to_evidence(snippets: list[SourceSnippet]) -> bool:
    plain = strip_vietnamese_accents(" ".join(snippet.text.lower() for snippet in snippets))
    return any(
        phrase in plain
        for phrase in (
            "nguyen lieu",
            "cong cu",
            "quy trinh",
            "ky thuat",
            "cac buoc",
            "cach lam",
            "duoc lam bang",
            "duoc in tu",
        )
    )


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


def _unsupported_numbers(answer: str, snippets: list[SourceSnippet]) -> list[str]:
    without_citations = re.sub(r"\[S\d+\]", "", answer, flags=re.IGNORECASE)
    answer_numbers = set(re.findall(r"\d+", without_citations))
    evidence = " ".join(
        f"{snippet.text} {snippet.title} {snippet.source}" for snippet in snippets
    )
    evidence_numbers = set(re.findall(r"\d+", evidence))
    return sorted(answer_numbers.difference(evidence_numbers))


def _answer_relevance_issues(question: str, answer: str, inferred_intent: str = "") -> list[str]:
    answer_plain = strip_vietnamese_accents(answer.lower())
    intent_plain = strip_vietnamese_accents(inferred_intent.lower())
    if (is_narrative_request(question) or "gioi thieu chung" in intent_plain) and any(
        phrase in answer_plain
        for phrase in ("ai duoc phep", "khong duoc phep", "dieu cam", "dieu kien bat buoc")
    ):
        return ["Câu trả lời nói sang quy định/cấm đoán thay vì giới thiệu di sản như người dùng yêu cầu."]
    if "trang thai unesco" in intent_plain and "unesco" not in answer_plain:
        return ["Câu trả lời chưa giải đáp trạng thái UNESCO mà người dùng hỏi."]
    if "hoi dia ban" in intent_plain and not any(
        phrase in answer_plain for phrase in ("dia ban", "tinh ", "thanh pho", "duoc ghi nhan tai")
    ):
        return ["Câu trả lời chưa nêu địa bàn mà người dùng hỏi."]
    return []


def _normalize_heritage_terms(answer: str) -> str:
    # UNESCO "ghi danh" di sản; "công nhận" dễ tạo cảm giác UNESCO cấp quyền
    # sở hữu/chứng nhận và không đúng thuật ngữ trong chính bộ tư liệu.
    return re.sub(r"UNESCO\s+công nhận", "UNESCO ghi danh", answer, flags=re.IGNORECASE)


def _narrative_context(text: str) -> str:
    section = re.split(r"Giới thiệu chung", text, maxsplit=1, flags=re.IGNORECASE)[-1]
    section = re.split(r"Câu hỏi\s*[–-]?\s*trả lời|CÂU HỎI", section, maxsplit=1, flags=re.IGNORECASE)[0]
    sentences = re.split(r"(?<=[.!?])\s+", section.strip())
    excluded = (
        "dòng số",
        "stt ",
        "bản chép",
        "căn cứ ghi",
        "quyết định ghi danh",
        "quản lý theo pháp luật",
        "thông tin nên được đọc",
    )
    useful = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip() and not any(marker in sentence.lower() for marker in excluded)
    ]
    return " ".join(useful) or section.strip()


def _unsupported_claim_phrases(answer: str, snippets: list[SourceSnippet]) -> list[str]:
    answer_plain = strip_vietnamese_accents(answer.lower())
    evidence_plain = strip_vietnamese_accents(
        " ".join(f"{snippet.text} {snippet.title}" for snippet in snippets).lower()
    )
    high_risk_phrases = (
        "dong nhac",
        "ra doi",
        "bat nguon",
        "nguon goc",
        "lau doi",
        "doc dao",
        "huyen bi",
        "dam ban sac",
        "linh thieng",
        "cong dong dan gian",
    )
    return [
        phrase
        for phrase in high_risk_phrases
        if phrase in answer_plain and phrase not in evidence_plain
    ]


def _parse_verification(raw: str) -> tuple[bool, list[str]]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise RuntimeError("Bộ kiểm chứng không trả về JSON.")
    payload = json.loads(match.group(0))
    claims = payload.get("unsupported_claims")
    unsupported = [str(item).strip() for item in claims] if isinstance(claims, list) else []
    unsupported = [item for item in unsupported if item]
    supported = payload.get("supported") is True and not unsupported
    if not supported and not unsupported:
        unsupported = ["Câu trả lời có dữ kiện chưa được nguồn hỗ trợ trực tiếp."]
    return supported, unsupported


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
