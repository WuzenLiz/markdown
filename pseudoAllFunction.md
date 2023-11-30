#Chart
---
## Table of contents
- [Table of contents](#table-of-contents)
- [Function](#function)
    - [Function: `get_api_info`](#function-get_api_info)
- [Action](#action)
    - [Action: `Setup channel`](#action-setup-channel)
    - [Action: `Pull channel`](#action-pull-channel)
---
## Function
### Function: `get_api_info`
> get_api_info là một function để lấy thông tin cần thiết để gọi api của channel
### Function: `get_channel_info`
> get_channel_info là một function để gọi và kiểm tra thông tin đã được cung cấp bởi channel
```mermaid
---
title: display_setup_channel flowchart
config:
    theme: forest
    curve: basis
---
flowchart LR
    Start([Start]) -->A[Controller Setup: Lấy thông tin của channel ] --> B[Channel: Gọi api] --> C{Thông tin của shop} 
    C --> |Không có thông tin| E[Trả về lỗi] --> End([End])
    C --> |Có thể gọi api| F[Trả về thông tin] --> End
```
### Function: `set_channel_identifier`
> set_channel_identifier là một function để lưu lại thông tin của channel
```mermaid 
---
title: set_channel_identifier flowchart
config: 
    theme: forest
    curve: basis
---
flowchart LR
A[display_setup_channel] --> b{response}
b --> |error| c[Trả về lỗi]
b --> |success| d[set_identifier: Thông tin của channel]
```

---
## Action
### Action: `Setup channel`
> Setup channel Là một action để lấy và kiểm tra thông tin của channel
- function required: 
    + `get_api_info: ->(dict)`: Trả về thông tin cần thiết để gọi api của channel
        Ex: A shopify channel will need: shop_name, api_password so this function will return a dict with 2 keys: shop_name and api_password
    + `get_channel_info: ->(Response)`: Gọi và kiểm tra thông tin đã được cung cấp bởi channel
    + `set_channel_identifier: ->(Response)`: Lưu lại thông tin của channel
- Flow:
```mermaid
    flowchart LR 
    A[get_api_info] --> B[get_channel_info] --> C[set_channel_identifier]
```
- Process:
```mermaid
---
title: Setup channel action
config: 
    theme: forest
    curve: basis
---
sequenceDiagram
    Actor A as litC_system
    box sync_core
        participant B as Controller
        participant D as State
        participant C as Channel
    end
    ACTOR E as Channel_system
    A->>+B:Request setup channel
    B->>+C:display_setup_channel
    C->>E:call check api
    activate E
    E-->>C:response
    deactivate E
    C-->>C:check response<br>validation api info
    par Response Error
        C-->>B:error
        B-->>A:error
    and Response Success
        C-->>B:success
        B-)D:save channel info
        B-->>A:success
        deactivate C
    end
    deactivate B
```
***
### Action: `Pull channel`
> Pull channel là một action để lấy thông tin(product,category,order,...) từ channel channel
- function required(for channel file only):
    + `Display_pull_channel: ->(Response)`: Thực hiện việc gọi api đến channel để lấy số lượng của `entity` cần pull. Sau khi lấy được số lượng thực hiện việc lưu vào `_state` của `entity` tương ứng
    + `get_{entity}_main_export: ->(Response: entity_Data)`: Thực hiện việc gọi APi để lấy dữ liệu của `entity` theo phân trang. Trả về data_pack chứa dữ liệu của `entity`
    + `get_{entity}_ext: ->(Response: entity_Data)`: Thực hiện việc bổ sung thêm dữ liệu của `entity` vào data_pack. Thường là các dữ liệu mà không thể lấy được thông qua api đâu tiên 
        Ex: metafield của product trong shopify
    + `check_{entity}_import`: (WIP)
    + `convert_{entity}_import: ->(entity_Data)`: Thực hiện việc chuyển đổi dữ liệu của `entity` thành dữ liệu của `entity` trong database. Cấu trúc của `entity` trong database được định nghĩa thông qua contruct class(model) của `entity`
    + `{entity}_import`: Thực hiện việc lưu dữ liệu của `entity` vào database
    + `after_{entity}_import`: Hâu xử lý sau khi lưu dữ liệu của `entity` vào database
    > **Note:** `"entity"` là tên của `entity` cần pull  
    function `{entity}_import` và `after_{entity}_import` được xử lý tại file warehouse.
    còn lại sẽ được xử lý tại file channel tương ứng với channel
- Flow:
```mermaid
    flowchart LR 
    A[Display_pull_channel] --> B[get_entity_main_export] --> C[get_entity_ext] --> D[check_entity_import] --> E[convert_entity_import] --> F[entity_import] --> G[after_entity_import]
```
- Chart:
    + Display_pull_channel
    ```mermaid
    ---
    title: Display_pull_channel flowchart
    config: 
        theme: forest
        curve: basis 
    ---
    flowchart LR
        A[Controller Pull: Lấy dữ liệu từ state ] --> B[Channel: Gọi api] --> C{Số lượng của entity} 
        C --> |Không có thông tin| E[Trả về lỗi]
        C --> |Có thể gọi api| F[Trả về/lưu vào state]
    ```

    + get_{entity}_main_export
    ```mermaid 
    ---
    title: get_{entity}_main_export flowchart tổng quát
    config: 
        theme: forest
        curve: basis 
    ---
    flowchart LR
     Start([Start])-->A[Lấy dữ liệu từ state] --> B[Khởi tạo params, request body] --> C[Truy vấn API] --> D[Xử lý] --> End([End: Trả về dữ liệu])
    ```

    ```mermaid
    ---
    title: get_{entity}_main_export flowchart chi tiết
    config: 
        theme: forest
        curve: basis 
    ---
    flowchart LR
    START([Start])-->A{kiểm tra trạng thái lần cuối}
    A --> |Đã hoàn thành| End([Trả về Response])
    A --> |Chưa hoàn thành| B[Khởi tạo params,<br>request body] --> C[Truy vấn API] --> D{Kiểm tra phân trang}
    D --> |Có phân trang: trang tiếp theo| E[Lưu lại url phân trang] --> F1{kiểm tra dữ liệu entity}
    D --> |không có phân trang| F1{kiểm tra dữ liệu entity} 
    F1 --> |Có dữ liệu| End
    F1 --> |Không có dữ liệu| G[Flag trạng thái<br>đã hoàn thành] --> End
    F1 --> |Có dữ liệu| G --> End
    F1 --> |Không có dữ liệu| G --> End
    ```

    + get_{entity}_ext
    ```mermaid
    ---
        title: get_{entity}_ext flowchart
        config: 
            theme: forest
            curve: basis
    ---
    flowchart LR
    START([Start])-->Data(maindata) --> A[Maindata id list]
    A --> B[Truy vấn API]
    B --> C[Merge dữ liệu] --> Data 
    B --> Q{next id}
    Q -->|true| A
    Q -->|false| End([Response Data])
    ```
    + check_{entity}_import
    > WIP

    + convert_{entity}_import
    ```mermaid
    ---
        title: convert_{entity}_import flowchart
        config: 
            theme: forest
            curve: basis
    ---
    flowchart LR
    START([Start])-->Data(entity_data) --> A[Check data] --> B[Convert data] --> End([Response Data])
    ```
