# Chatbot API Integration Guide

## Introduction

This guide provides documentation for the Inventory Management System API, specifically tailored for integration with a chatbot. It details the relevant endpoints, data formats, authentication, and common workflows verified through testing and simulations.

**Base URL:** `http://127.0.0.1:8000` (Note: This may differ in production environments)

## Capabilities Summary

Based on verified endpoints, a chatbot integrating with this API can perform the following actions:

- **Search for Products:** Find products by name.
- **Check Availability:** Get the current stock status (`in_stock`, `low_stock`, `out_of_stock`) and quantity for a specific product.
- **Place Orders:**
  - Create standard orders with multiple items.
  - Place quick orders for single items, optionally defaulting the quantity based on the customer's history.
- **Retrieve Order Information:** Get details of a specific past order.
- **View Customer History:** Access a customer's order history and identify frequently purchased items.
- **Discover Products:** Retrieve a list of featured products.
- **Check System Health:** Verify the API is operational.
- **Modify Pending Orders:** Change the items (products and quantities) within an existing order that has not yet been processed (status 'pending').
- **Cancel Pending Orders:** Cancel an entire order that has not yet been processed (status 'pending'), restoring inventory.
- **Download Inventory:** Retrieve the entire current inventory as a CSV file.
- **Upload Inventory:** Update inventory quantities in bulk via CSV upload.
- **Delete Products:** Permanently remove a product and its associated inventory record.

## Authentication

All API requests require authentication via an API key. The key must be included as a query parameter named `api_key` in every request.

**Example:**
`GET http://127.0.0.1:8000/api/products/search/?query=apple&api_key=YOUR_API_KEY_HERE`

If the API key is missing or invalid, the API will respond with a `401 Unauthorized` status code.

```json
{
  "detail": "Invalid or missing API key"
}
```

## General Error Handling

Besides authentication errors, the API uses standard HTTP status codes:

- `200 OK`: Request successful.
- `201 Created`: Resource created successfully (e.g., Order).
- `404 Not Found`: The requested resource (e.g., product, order, inventory record) does not exist.
  ```json
  { "detail": "Product not found" }
  ```
- `422 Unprocessable Entity`: The request data is invalid (e.g., missing required fields, invalid data types). Details are usually provided.
  ```json
  {
    "detail": [
      {
        "loc": ["body", "field_name"],
        "msg": "validation error message",
        "type": "value_error"
      }
    ]
  }
  ```
- `400 Bad Request`: A general client-side error, often used for business logic failures (e.g., insufficient inventory during order creation).
  ```json
  { "detail": "Insufficient inventory for product X" }
  ```
- `500 Internal Server Error`: An unexpected error occurred on the server.

## Endpoint Reference

### Products

#### Search Products

- **Endpoint:** `GET /api/products/search/`
- **Description:** Searches for products by name (case-insensitive).
- **Query Parameters:**
  - `query` (string, required): The search term.
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):** An array of product objects matching the query.
  ```json
  [
    {
      "name": "Simulation Apple",
      "description": "Fresh red apples",
      "unit": "kg",
      "price_per_unit": 2.5,
      "custom_properties": null,
      "id": 318
    },
    {
      "name": "Apple Pie Filling",
      "description": "Ready-to-use apple filling",
      "unit": "can",
      "price_per_unit": 3.5,
      "custom_properties": { "brand": "BakeryDelight" },
      "id": 123
    }
  ]
  ```
- **Notes:** Returns an empty array `[]` if no products match.

#### Get Featured Products

- **Endpoint:** `GET /api/products/featured`
- **Description:** Retrieves a list of featured products (currently based on highest inventory quantity).
- **Query Parameters:**
  - `limit` (integer, optional, default: 5): Maximum number of featured products to return.
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):** An array of featured product objects, including availability and quantity.
  ```json
  [
    {
      "id": 320,
      "name": "Simulation Carrot",
      "description": "Organic carrots",
      "unit": "kg",
      "price_per_unit": 1.2,
      "available": true,
      "quantity": 150.0,
      "custom_properties": null
    },
    {
      "id": 318,
      "name": "Simulation Apple",
      "description": "Fresh red apples",
      "unit": "kg",
      "price_per_unit": 2.5,
      "available": true,
      "quantity": 100.0,
      "custom_properties": null
    }
    // ... potentially more products up to the limit
  ]
  ```

#### Get Product Details

- **Endpoint:** `GET /api/products/{product_id}`
- **Description:** Retrieves details for a specific product. Useful for getting full details after a search or from an order history item.
- **Path Parameters:**
  - `product_id` (integer, required): The ID of the product.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):** A single product object.
  ```json
  {
    "name": "Simulation Apple",
    "description": "Fresh red apples",
    "unit": "kg",
    "price_per_unit": 2.5,
    "custom_properties": null,
    "id": 318
  }
  ```
- **Error Response (`404 Not Found`):** If the `product_id` does not exist.

#### Delete Product

- **Endpoint:** `DELETE /api/products/{product_id}`
- **Description:** Deletes a specific product and its associated inventory record (if one exists).
- **Path Parameters:**
  - `product_id` (integer, required): The ID of the product to delete.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Success Response (`204 No Content`):** Indicates successful deletion. No response body.
- **Error Response (`404 Not Found`):** If the `product_id` does not exist.
- **Notes:** This is a permanent deletion. Ensure the product is no longer needed before using this endpoint.

### Inventory

#### Get Inventory Status

- **Endpoint:** `GET /api/inventory/status/{product_id}`
- **Description:** Checks the current inventory status and quantity for a specific product.
- **Path Parameters:**
  - `product_id` (integer, required): The ID of the product.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):**
  ```json
  {
    "status": "in_stock", // "in_stock", "low_stock", or "out_of_stock"
    "quantity": 40.0
  }
  ```
- **Error Response (`404 Not Found`):** If the `product_id` does not exist.

#### Download Inventory CSV

- **Endpoint:** `GET /api/inventory/download`
- **Description:** Downloads the entire current inventory, including product details, as a CSV file.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):**
  - **Headers:**
    - `Content-Type: text/csv`
    - `Content-Disposition: attachment; filename="inventory.csv"`
  - **Body:** A CSV formatted string with the following columns:
    - `product_id`
    - `name`
    - `unit`
    - `price_per_unit`
    - `quantity` (Current inventory quantity)
    - `last_updated` (Timestamp of last inventory update)
- **Example CSV Output:**
  ```csv
  product_id,name,unit,price_per_unit,quantity,last_updated
  318,"Simulation Apple",kg,2.5,98.0,"2025-04-02T05:10:00.123Z"
  319,"Simulation Banana",kg,1.95,49.0,"2025-04-02T05:10:00.123Z"
  320,"Simulation Carrot",kg,1.2,150.0,"2025-04-01T08:00:00.000Z"
  ```
- **Error Responses:** Standard authentication errors apply.

#### Upload Inventory CSV

- **Endpoint:** `POST /api/inventory/upload`
- **Description:** Updates inventory quantities in bulk by uploading a CSV file. It can update existing inventory records or create new ones if a product exists but has no inventory entry yet.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Request Body:**
  - `multipart/form-data` containing a file field (e.g., named `file`).
  - The uploaded file must be a CSV with the following columns in the header row:
    - `product_id`
    - `quantity`
- **Example CSV Input:**
  ```csv
  product_id,quantity
  318,105.0
  319,55
  321,10  # Assumes product 321 exists but might not have inventory yet
  ```
- **Success Response (`200 OK`):** A JSON summary of the operation.
  ```json
  {
    "processed_rows": 3, // Total rows read from CSV (excluding header)
    "updated_count": 3, // Rows successfully processed (updated or created)
    "errors": [
      // List of errors encountered
      // Example error if a product ID doesn't exist:
      // { "row_number": 4, "error_message": "Product ID 999 not found." }
      // Example error for invalid quantity format:
      // { "row_number": 5, "error_message": "Invalid data type - invalid literal for int() with base 10: 'abc'" }
    ]
  }
  ```
  _Note: The exact structure of the success response depends on the `CSVUploadResponse` model definition in `csv_service.py`._
- **Error Responses:**
  - `400 Bad Request`: If the CSV file format is invalid (e.g., wrong headers, incorrect number of columns, non-numeric quantity, negative quantity) or if the file type is not CSV (`{"detail": "CSV Parsing Error: ..."}` or `{"detail": "Invalid file type..."}`).
  - `422 Unprocessable Entity`: If the request is missing the file.
  - `500 Internal Server Error`: If an unexpected error occurs during processing or database update.
  - Standard authentication errors apply.

### Orders

#### Create Standard Order

- **Endpoint:** `POST /api/orders`
- **Description:** Creates a new order with one or more items for a customer. Inventory is checked and deducted upon successful creation.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Request Body:**
  ```json
  {
    "customer_id": "user_chatbot_123",
    "items": [
      { "product_id": 318, "quantity": 2.5 },
      { "product_id": 319, "quantity": 1.0 }
    ]
  }
  ```
- **Success Response (`201 Created`):** The newly created order details, including the calculated total.
  ```json
  {
    "id": 69,
    "customer_id": "user_chatbot_123",
    "status": "pending",
    "created_at": "2025-04-02T01:30:00.123456",
    "updated_at": "2025-04-02T01:30:00.123456",
    "items": [
      { "product_id": 318, "quantity": 2.5, "price_at_order": 2.5 },
      { "product_id": 319, "quantity": 1.0, "price_at_order": 1.95 }
    ],
    "total": 8.2 // (2.5 * 2.5) + (1.0 * 1.95)
  }
  ```
- **Error Responses:**
  - `404 Not Found`: If any `product_id` in `items` does not exist.
  - `400 Bad Request`: If inventory is insufficient for any item (`{"detail": "Insufficient inventory for product X"}`).
  - `422 Unprocessable Entity`: If request body is invalid (e.g., missing fields, quantity <= 0).

#### Create Quick Order

- **Endpoint:** `POST /api/orders/quick`
- **Description:** Quickly creates an order for a _single_ product. If `quantity` is omitted, it defaults to the quantity from the customer's most recent previous order of that specific product, or 1.0 if no history exists for that item.
- **Query Parameters:**
  - `customer_id` (string, required): The customer's identifier.
  - `product_id` (integer, required): The ID of the product to order.
  - `quantity` (float, optional): The quantity to order. If omitted, defaults based on history or to 1.0.
  - `api_key` (string, required): Your API key.
- **Success Response (`201 Created`):** The newly created order details.
  ```json
  {
    "id": 68,
    "customer_id": "sim_customer_orders",
    "status": "pending",
    "created_at": "2025-04-02T01:15:19.902032",
    "updated_at": "2025-04-02T01:15:19.902036",
    "items": [
      { "product_id": 317, "quantity": 3.0, "price_at_order": 9.95 } // Quantity was 3 in params
    ],
    "total": 29.849999999999998
  }
  ```
  ```json
  // Example response if quantity was omitted and defaulted based on history (e.g., last order was 5 units)
  {
    "id": 70,
    "customer_id": "sim_customer_orders",
    "status": "pending",
    "created_at": "2025-04-02T01:35:00.123456",
    "updated_at": "2025-04-02T01:35:00.123456",
    "items": [
      { "product_id": 317, "quantity": 5.0, "price_at_order": 9.95 } // Quantity defaulted to 5.0 from history
    ],
    "total": 49.75
  }
  ```
- **Error Responses:**
  - `404 Not Found`: If the `product_id` does not exist.
  - `400 Bad Request`: If inventory is insufficient.
  - `422 Unprocessable Entity`: If `quantity` is provided and is <= 0.

#### Get Order Details

- **Endpoint:** `GET /api/orders/{order_id}`
- **Description:** Retrieves details for a specific order.
- **Path Parameters:**
  - `order_id` (integer, required): The ID of the order.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):** The order details, including the correctly calculated total.
  ```json
  {
    "id": 67,
    "customer_id": "sim_customer_orders",
    "status": "pending",
    "created_at": "2025-04-02T01:15:16.095430",
    "updated_at": "2025-04-02T01:15:16.095443",
    "items": [{ "product_id": 317, "quantity": 5.0, "price_at_order": 9.95 }],
    "total": 49.75
  }
  ```
- **Error Response (`404 Not Found`):** If the `order_id` does not exist.

#### Get Customer Order History

- **Endpoint:** `GET /api/orders/customer/{customer_id}/history`
- **Description:** Retrieves the order history for a specific customer, including frequently ordered products.
- **Path Parameters:**
  - `customer_id` (string, required): The customer's identifier.
- **Query Parameters:**
  - `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):**
  ```json
  {
    "customer_id": "sim_customer_001",
    "order_count": 4,
    "frequent_products": [
      // Sorted by frequency (descending)
      { "product_id": 316, "frequency": 1 },
      { "product_id": 306, "frequency": 1 },
      { "product_id": 257, "frequency": 1 },
      { "product_id": 256, "frequency": 1 }
    ]
  }
  ```
- **Notes:** Returns `order_count: 0` and `frequent_products: []` if the customer has no orders.

#### Modify Order Items (Pending Orders Only)

- **Endpoint:** `PUT /api/orders/{order_id}/items`
- **Description:** Replaces all items in a specific _pending_ order with a new set of items. Inventory is adjusted accordingly (old items restored, new items deducted).
- **Path Parameters:**
- `order_id` (integer, required): The ID of the pending order to modify.
- **Query Parameters:**
- `api_key` (string, required): Your API key.
- **Request Body:**

```json
{
  "items": [
    { "product_id": 325, "quantity": 2.0 }
    // Include all desired items for the modified order
  ]
}
```

- **Success Response (`200 OK`):** The updated order details with the new items and recalculated total.

```json
{
  "id": 71,
  "customer_id": "sim_customer_orders",
  "status": "pending",
  "created_at": "2025-04-02T02:31:56.594602",
  "updated_at": "2025-04-02T02:32:00.934791", // Note updated timestamp
  "items": [{ "product_id": 325, "quantity": 2.0, "price_at_order": 24.5 }],
  "total": 49.0 // New total based on modified items
}
```

- **Error Responses:**
- `404 Not Found`: If the `order_id` does not exist, or if any `product_id` in the new `items` does not exist.
- `400 Bad Request`:
  - If the order status is not 'pending' (`{"detail": "Order status is 'X', cannot modify items."}`).
  - If inventory is insufficient for any _new_ item (`{"detail": "Insufficient inventory for product Y..."}`).
- `422 Unprocessable Entity`: If request body is invalid (e.g., empty `items` list, quantity <= 0).

#### Cancel Order (Pending Orders Only)

- **Endpoint:** `POST /api/orders/{order_id}/cancel`
- **Description:** Cancels a specific _pending_ order. Inventory for all items in the order is restored.
- **Path Parameters:**
- `order_id` (integer, required): The ID of the pending order to cancel.
- **Query Parameters:**
- `api_key` (string, required): Your API key.
- **Success Response (`200 OK`):** The order details with the status updated to 'cancelled'.

```json
{
  "id": 72,
  "customer_id": "sim_customer_orders",
  "status": "cancelled", // Status changed
  "created_at": "2025-04-02T02:32:06.264020",
  "updated_at": "2025-04-02T02:32:09.772114", // Note updated timestamp
  "items": [{ "product_id": 324, "quantity": 3.0, "price_at_order": 9.95 }],
  "total": 29.849999999999998
}
```

- **Error Responses:**
- `404 Not Found`: If the `order_id` does not exist.
- `400 Bad Request`: If the order status is not 'pending' (`{"detail": "Order status is 'X', cannot cancel."}`).

### System

#### Health Check

- **Endpoint:** `GET /api/system/health`
- **Description:** Checks the health of the API. Does not require authentication.
- **Success Response (`200 OK`):**
  ```json
  {
    "status": "healthy",
    "timestamp": "2025-04-02T01:40:00.123456+00:00",
    "version": "1.0.0"
  }
  ```

## Chatbot Workflow Examples

These examples show common sequences of API calls a chatbot might make. Remember to include the `api_key` query parameter in all requests.

### Workflow 1: Checking Product Availability

1.  **User asks:** "Do you have Simulation Apples?"
2.  **Chatbot:** Calls `GET /api/products/search/?query=Simulation Apple`
3.  **API Response:** `[{"id": 318, "name": "Simulation Apple", ...}]`
4.  **Chatbot:** Extracts `product_id` (318).
5.  **Chatbot:** Calls `GET /api/inventory/status/318`
6.  **API Response:** `{"status": "in_stock", "quantity": 100.0}`
7.  **Chatbot responds to user:** "Yes, we have 100.0 kg of Simulation Apples in stock." (Or similar based on status/quantity).

### Workflow 2: Placing Order via Search

1.  **User asks:** "I want to order 2 kg of Simulation Apples."
2.  **Chatbot:** Calls `GET /api/products/search/?query=Simulation Apple` (to confirm product and get ID).
3.  **API Response:** `[{"id": 318, "name": "Simulation Apple", ...}]`
4.  **Chatbot:** Extracts `product_id` (318).
5.  **Chatbot:** Calls `POST /api/orders` with body:
    ```json
    {
      "customer_id": "user_chatbot_123",
      "items": [{ "product_id": 318, "quantity": 2.0 }]
    }
    ```
6.  **API Response (`201 Created`):** Order details including `id` and `total`.
7.  **Chatbot responds to user:** "Okay, I've placed your order for 2.0 kg of Simulation Apples. Your order ID is X and the total is Y."
8.  _(Error Handling):_ If API returns 400 (Insufficient Inventory), inform the user. If 404, inform the user the product wasn't found.

### Workflow 3: Reordering Frequent Item

1.  **User asks:** "Reorder my usual." or "What do I order often?"
2.  **Chatbot:** Calls `GET /api/orders/customer/user_chatbot_123/history`
3.  **API Response:** `{"customer_id": "user_chatbot_123", "order_count": 5, "frequent_products": [{"product_id": 318, "frequency": 3}, {"product_id": 319, "frequency": 2}]}`
4.  **Chatbot:** Identifies the most frequent product (ID 318). _Optional: Ask user to confirm reordering this item._
5.  **Chatbot:** Calls `POST /api/orders/quick?customer_id=user_chatbot_123&product_id=318` (Omits quantity to use default logic).
6.  **API Response (`201 Created`):** Order details, including the quantity determined by the API (e.g., based on the last order of product 318).
7.  **Chatbot responds to user:** "Okay, I've reordered [Quantity] [Unit] of [Product Name] for you. Your order ID is Z."

### Workflow 4: Getting Featured Items

1.  **User asks:** "What's popular?" or "Show me featured items."
2.  **Chatbot:** Calls `GET /api/products/featured?limit=3`
3.  **API Response:** Array of featured product objects.
    ```json
    [
      {"id": 320, "name": "Simulation Carrot", ..., "quantity": 150.0, "available": true},
      {"id": 318, "name": "Simulation Apple", ..., "quantity": 100.0, "available": true},
      // ...
    ]
    ```
4.  **Chatbot displays featured items to the user.**

### Workflow 5: Modifying a Pending Order

1.  **User asks:** "Can I change my last order (ID 71)?"
2.  **Chatbot:** Calls `GET /api/orders/71` to check current status and items.
3.  **API Response:** Order details, including `status: "pending"` and current items.
4.  **Chatbot confirms with user:** "Your order 71 is still pending. It contains [Current Items]. What would you like to change it to?"
5.  **User responds:** "Change it to 2 units of Product B (ID 325) instead."
6.  **Chatbot:** Calls `PUT /api/orders/71/items` with body:
    ```json
    {
      "items": [{ "product_id": 325, "quantity": 2.0 }]
    }
    ```
7.  **API Response (`200 OK`):** Updated order details.
8.  **Chatbot responds to user:** "Okay, I've updated order 71 to contain 2 units of Product B. The new total is Y."
9.  _(Error Handling):_ If API returns 400 (not pending), inform user it's too late. If 400 (insufficient inventory), inform user.

### Workflow 6: Cancelling a Pending Order

1.  **User asks:** "Please cancel my last order (ID 72)."
2.  **Chatbot:** Calls `GET /api/orders/72` to check current status.
3.  **API Response:** Order details, including `status: "pending"`.
4.  **Chatbot:** Calls `POST /api/orders/72/cancel`.
5.  **API Response (`200 OK`):** Order details with `status: "cancelled"`.
6.  **Chatbot responds to user:** "Okay, I have cancelled your order 72."
7.  _(Error Handling):_ If API returns 400 (not pending), inform user it's too late to cancel. If 404, inform user the order wasn't found.
