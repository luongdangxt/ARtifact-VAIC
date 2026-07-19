using System;
using ARtifact.Core;

namespace ARtifact.Conversation
{
    public enum ChatRole
    {
        User,
        Artisan
    }

    /// <summary>Một tin nhắn trong cuộc hội thoại.</summary>
    [Serializable]
    public struct ChatMessage
    {
        public ChatRole Role;
        public string Text;

        public ChatMessage(ChatRole role, string text)
        {
            Role = role;
            Text = text;
        }
    }

    /// <summary>
    /// Ngữ cảnh về nghệ nhân đang trò chuyện, gửi kèm câu hỏi để backend/LLM trả lời
    /// đúng nhân vật và đúng di sản.
    /// </summary>
    public struct ArtisanContext
    {
        public ArtisanId Id;
        public string DisplayName;
        public string Description;

        public ArtisanContext(ArtisanId id, string displayName, string description)
        {
            Id = id;
            DisplayName = displayName;
            Description = description;
        }
    }
}
