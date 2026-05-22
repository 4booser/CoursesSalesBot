public class User {
    public int Id { get; set; }
    public string Token { get; set; }
    public SubscribeType SubscribeType { get; set; }
}

public enum SubscribeType {
    Free,
    Premium,
}
    