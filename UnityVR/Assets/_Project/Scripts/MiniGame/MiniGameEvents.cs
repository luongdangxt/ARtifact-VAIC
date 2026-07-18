namespace ARtifact.MiniGame
{
    /// <summary>Người chơi vừa hoàn tất một nét vẽ (hạ bút → nhấc bút).</summary>
    public readonly struct StrokeCompletedEvent
    {
        /// <summary>Tổng số nét đã vẽ tính đến hiện tại.</summary>
        public readonly int Count;
        public StrokeCompletedEvent(int count) => Count = count;
    }

    /// <summary>Đã vẽ đủ số nét yêu cầu và một bức tranh Đông Hồ được hé lộ.</summary>
    public readonly struct PaintingRevealedEvent
    {
        /// <summary>Chỉ số bức tranh (0..N-1) trong danh sách material của mini-game.</summary>
        public readonly int PaintingIndex;
        public PaintingRevealedEvent(int paintingIndex) => PaintingIndex = paintingIndex;
    }
}
