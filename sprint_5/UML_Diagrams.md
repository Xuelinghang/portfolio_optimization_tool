' Define the User class
class User {
  + id: Integer
  + username: String
  + email: String
  + password_hash: String
}

' Define the Asset class
class Asset {
  + id: Integer
  + symbol: String
  + asset_type: String
  + user_id: Integer
}

' Define the Portfolio class
class Portfolio {
  + id: Integer
  + user_id: Integer
  + portfolio_name: String
  + portfolio_data: Text
  + purchase_date: DateTime
}

' Define the MarketData class
class MarketData {
  + id: Integer
  + asset_id: Integer
  + date: DateTime
  + price: Float
}

' Define the Transaction class
class Transaction {
  + id: Integer
  + user_id: Integer
  + asset_id: Integer
  + portfolio_id: Integer
  + transaction_type: String
  + quantity: Float
  + price: Float
  + transaction_date: DateTime
  + fees: Float
  + notes: Text
}

' Relationships
User "1" -- "*" Asset : owns
User "1" -- "*" Portfolio : has
User "1" -- "*" Transaction : makes

Asset "1" -- "*" MarketData : collects
Asset "1" -- "*" Transaction : involved in

Portfolio "1" -- "*" Transaction : contains