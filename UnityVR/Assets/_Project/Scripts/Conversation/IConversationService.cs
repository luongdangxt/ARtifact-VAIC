using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace ARtifact.Conversation
{
    /// <summary>
    /// Quản lý một phiên hội thoại với nghệ nhân: giữ lịch sử, gửi câu hỏi qua
    /// <see cref="ILLMClient"/> và trả về câu trả lời. Stub cho giai đoạn 1.
    /// </summary>
    public interface IConversationService
    {
        IReadOnlyList<ChatMessage> History { get; }

        Task<string> AskAsync(string question, ArtisanContext context, CancellationToken cancellationToken = default);

        void Reset();
    }
}
