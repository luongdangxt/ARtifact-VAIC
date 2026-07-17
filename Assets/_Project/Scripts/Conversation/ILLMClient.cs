using System.Threading;
using System.Threading.Tasks;

namespace ARtifact.Conversation
{
    /// <summary>
    /// Cổng tới nguồn sinh câu trả lời cho nghệ nhân. Giai đoạn 1 chưa cài đặt —
    /// giai đoạn sau thêm lớp <c>BackendLLMClient</c> gọi API backend của bạn mà
    /// KHÔNG cần đụng module nào khác.
    /// </summary>
    public interface ILLMClient
    {
        Task<string> AskAsync(string question, ArtisanContext context, CancellationToken cancellationToken = default);
    }
}
