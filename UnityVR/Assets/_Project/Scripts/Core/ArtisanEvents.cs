namespace ARtifact.Core
{
    /// <summary>Nghệ nhân vừa xuất hiện (marker được nhận diện, model đã spawn).</summary>
    public readonly struct ArtisanAppearedEvent
    {
        public readonly IArtisanDefinition Artisan;
        public ArtisanAppearedEvent(IArtisanDefinition artisan) => Artisan = artisan;
    }

    /// <summary>Nghệ nhân biến mất (mất tracking marker).</summary>
    public readonly struct ArtisanDisappearedEvent
    {
        public readonly ArtisanId Id;
        public ArtisanDisappearedEvent(ArtisanId id) => Id = id;
    }

    /// <summary>Người dùng chọn/chạm vào nghệ nhân (dùng cho UI, mở hội thoại sau này).</summary>
    public readonly struct ArtisanSelectedEvent
    {
        public readonly ArtisanId Id;
        public ArtisanSelectedEvent(ArtisanId id) => Id = id;
    }
}
