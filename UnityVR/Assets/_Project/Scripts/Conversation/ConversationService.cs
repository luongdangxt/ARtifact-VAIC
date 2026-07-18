using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace ARtifact.Conversation
{
    /// <summary>
    /// Cài đặt mặc định của <see cref="IConversationService"/>: giữ lịch sử hội thoại và
    /// uỷ thác việc sinh câu trả lời cho <see cref="ILLMClient"/> (được tiêm vào).
    /// </summary>
    public sealed class ConversationService : IConversationService
    {
        private readonly ILLMClient _llm;
        private readonly List<ChatMessage> _history = new();

        public ConversationService(ILLMClient llm)
        {
            _llm = llm;
        }

        public IReadOnlyList<ChatMessage> History => _history;

        public async Task<string> AskAsync(string question, ArtisanContext context, CancellationToken cancellationToken = default)
        {
            _history.Add(new ChatMessage(ChatRole.User, question));
            var answer = await _llm.AskAsync(question, context, cancellationToken);
            _history.Add(new ChatMessage(ChatRole.Artisan, answer));
            return answer;
        }

        public void Reset() => _history.Clear();
    }
}
