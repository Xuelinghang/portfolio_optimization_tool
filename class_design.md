+----------------+          +---------------------+          +----------------+
|     User       |          |     Portfolio       |          |     Asset      |
+----------------+          +---------------------+          +----------------+
| user_id (PK)   |<-----1:M-| portfolio_id (PK)   |<-----1:M-| asset_id (PK)  |
| email          |          | user_id (FK)        |          | portfolio_id   |
| role           |          | name                |          | symbol         |
| hashed_password|          | created_at          |          | quantity       |
+----------------+          | updated_at          |          | purchase_price |
                            +---------------------+          +----------------+
                                     |                                  |
                                     |                                  | M:1
                                     |                                  |
                                     |          +---------------------+ |
                                     +--------->|   MarketData        |
                                                +---------------------+
                                                | symbol (PK)         |
                                                | price               |
                                                | timestamp           |
                                                | asset_type          |
                                                +---------------------+