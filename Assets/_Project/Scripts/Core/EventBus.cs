using System;
using System.Collections.Generic;

namespace ARtifact.Core
{
    /// <summary>
    /// Cài đặt mặc định của <see cref="IEventBus"/>. Một instance được tạo ở
    /// composition root (AppBootstrap) và tiêm vào các service.
    /// </summary>
    public sealed class EventBus : IEventBus
    {
        // Mỗi kiểu message giữ một delegate riêng, khoá theo Type.
        private readonly Dictionary<Type, Delegate> _handlers = new();

        public void Publish<T>(in T message) where T : struct
        {
            if (_handlers.TryGetValue(typeof(T), out var d) && d is Action<T> action)
            {
                action.Invoke(message);
            }
        }

        public void Subscribe<T>(Action<T> handler) where T : struct
        {
            if (handler == null) return;
            _handlers.TryGetValue(typeof(T), out var existing);
            _handlers[typeof(T)] = (existing as Action<T>) + handler;
        }

        public void Unsubscribe<T>(Action<T> handler) where T : struct
        {
            if (handler == null) return;
            if (_handlers.TryGetValue(typeof(T), out var existing) && existing is Action<T> current)
            {
                var updated = current - handler;
                if (updated == null) _handlers.Remove(typeof(T));
                else _handlers[typeof(T)] = updated;
            }
        }
    }
}
