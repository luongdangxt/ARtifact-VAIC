using System.Threading;
using System.Threading.Tasks;

namespace ARtifact.Conversation
{
    /// <summary>
    /// Cài đặt tạm cho giai đoạn 1 (chưa nối backend). Trả về một câu placeholder để
    /// pipeline hội thoại chạy được end-to-end. Giai đoạn sau thay bằng BackendLLMClient.
    /// </summary>
    public sealed class OfflineLLMClient : ILLMClient
    {
        public Task<string> AskAsync(string question, ArtisanContext context, CancellationToken cancellationToken = default)
        {
            var name = string.IsNullOrEmpty(context.DisplayName) ? "Nghệ nhân" : context.DisplayName;
            return Task.FromResult(
                $"({name} — chưa kết nối AI) Xin chào, tôi sẽ trả lời câu hỏi \"{question}\" khi backend được tích hợp.");
        }
    }
}
