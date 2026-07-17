using System;

namespace ARtifact.Core
{
    /// <summary>
    /// Bus sự kiện gõ kiểu (typed) để các module giao tiếp mà không tham chiếu trực tiếp
    /// lẫn nhau. AR phát sự kiện; UI/Conversation lắng nghe — không module nào cần biết
    /// module kia tồn tại.
    /// </summary>
    public interface IEventBus
    {
        void Publish<T>(in T message) where T : struct;
        void Subscribe<T>(Action<T> handler) where T : struct;
        void Unsubscribe<T>(Action<T> handler) where T : struct;
    }
}
