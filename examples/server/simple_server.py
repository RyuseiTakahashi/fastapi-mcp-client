"""
Simple FastAPI MCP Server Example with Item API.

This server demonstrates how to create a FastAPI application with MCP support
and provides a simple Item API.

Run with:
    uvicorn simple_server:app --reload
"""

from fastapi import FastAPI, HTTPException, status, Path, Query, Body
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# Create the FastAPI application
app = FastAPI(
    title="FastAPI MCP Item API",
    description="A simple server demonstrating MCP/SSE capabilities with an Item API",
    version="0.1.0",
)

# データモデルの定義
class Item(BaseModel):
    id: int = Field(
        ..., 
        description="アイテムの一意ID",
    )
    name: str = Field(
        ..., 
        description="アイテムの名前",
        example="ノートPC",
        min_length=1,
        max_length=100
    )
    description: Optional[str] = Field(
        None, 
        description="アイテムの詳細説明（オプション）",
        example="高性能プログラミング用ノートパソコン"
    )
    price: float = Field(
        ..., 
        description="アイテムの価格（日本円）",
        example=150000,
        gt=0
    )
    tags: List[str] = Field(
        [], 
        description="アイテムに関連するタグのリスト",
        example=["電子機器", "コンピュータ"]
    )
    
    class Config:
        schema_extra = {
            "description": "商品情報を表すモデル",
        }

# 新規アイテム作成用のリクエストモデル (IDはサーバー側で割り当てるため除外)
class ItemCreate(BaseModel):
    name: str = Field(
        ..., 
        description="新規作成するアイテムの名前",
        example="ヘッドフォン",
        min_length=1,
        max_length=100
    )
    description: Optional[str] = Field(
        None, 
        description="作成するアイテムの詳細説明（オプション）",
        example="ノイズキャンセリング機能付きワイヤレスヘッドフォン"
    )
    price: float = Field(
        ..., 
        description="作成するアイテムの価格（日本円）",
        example=25000,
        gt=0
    )
    tags: List[str] = Field(
        [], 
        description="作成するアイテムに関連するタグのリスト",
        example=["電子機器", "オーディオ"]
    )
    
    class Config:
        schema_extra = {
            "description": "新規アイテム作成リクエスト",
        }

# アイテム更新用のリクエストモデル (すべてのフィールドをオプショナルに)
class ItemUpdate(BaseModel):
    name: Optional[str] = Field(
        None, 
        description="更新するアイテム名（指定した場合のみ更新）",
        example="Bluetoothヘッドフォン",
        min_length=1,
        max_length=100
    )
    description: Optional[str] = Field(
        None, 
        description="更新するアイテムの詳細説明（指定した場合のみ更新）",
        example="高音質ノイズキャンセリング機能付きワイヤレスヘッドフォン"
    )
    price: Optional[float] = Field(
        None, 
        description="更新するアイテムの価格（指定した場合のみ更新）",
        example=28000,
        gt=0
    )
    tags: Optional[List[str]] = Field(
        None, 
        description="更新するアイテムのタグリスト（指定した場合のみ更新）",
        example=["電子機器", "オーディオ", "Bluetooth"]
    )
    
    class Config:
        schema_extra = {
            "description": "アイテム更新リクエスト。更新したいフィールドのみを含めることができます。",
        }

# レスポンスモデル
class DeleteResponse(BaseModel):
    status: str = Field(..., description="操作結果のステータス", example="success")
    message: str = Field(..., description="操作結果の詳細メッセージ", example="Item 1 deleted successfully")
    deleted_item: Item = Field(..., description="削除されたアイテムの情報")

# エラーレスポンスモデル
class ErrorResponse(BaseModel):
    detail: str = Field(..., description="エラーの詳細情報", example="Item not found")

# インメモリデータストア
items_db = {}

# サンプルデータの追加
sample_items = [
    Item(id=1, name="ノートPC", description="プログラミング用ノートPC", price=150000, tags=["電子機器", "コンピュータ"]),
    Item(id=2, name="キーボード", description="メカニカルキーボード", price=15000, tags=["電子機器", "アクセサリ"]),
    Item(id=3, name="モニター", description="4Kモニター", price=50000, tags=["電子機器", "ディスプレイ"]),
]

for item in sample_items:
    items_db[item.id] = item

# APIエンドポイントの定義
@app.get(
    "/items/",
    response_model=List[Item],
    summary="全アイテム一覧取得",
    description="データベースに保存されているすべてのアイテムのリストを取得します。アイテムが存在しない場合は空のリストを返します。",
    tags=["items"],
    operation_id="list_items",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "アイテムリストの取得に成功",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": 1,
                            "name": "ノートPC",
                            "description": "プログラミング用ノートPC",
                            "price": 150000,
                            "tags": ["電子機器", "コンピュータ"]
                        },
                        {
                            "id": 2,
                            "name": "キーボード",
                            "description": "メカニカルキーボード",
                            "price": 15000,
                            "tags": ["電子機器", "アクセサリ"]
                        }
                    ]
                }
            }
        }
    }
)
async def list_items():
    """
    すべてのアイテムを一覧表示します。
    
    データベースに登録されているすべてのアイテムの情報を取得し、リストとして返します。
    """
    return list(items_db.values())


@app.get(
    "/items/{item_id}",
    response_model=Item,
    summary="アイテム詳細取得",
    description="指定されたIDのアイテム詳細情報を取得します。アイテムが存在しない場合は404エラーを返します。",
    tags=["items"],
    operation_id="get_item",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "アイテムの取得に成功",
            "model": Item
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "指定されたIDのアイテムが見つからない",
            "model": ErrorResponse
        }
    }
)
async def get_item(
    item_id: int = Path(
        ..., 
        description="取得するアイテムのID", 
        example=1,
        gt=0,
        title="アイテムID"
    )
):
    """
    特定のアイテムを取得します。
    
    指定されたIDに対応するアイテムをデータベースから取得します。アイテムが存在しない場合は404エラーを返します。
    """
    if item_id not in items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Item not found"
        )
    return items_db[item_id]


@app.post(
    "/items/",
    response_model=Item,
    summary="新規アイテム作成",
    description="新しいアイテムをデータベースに作成します。作成されたアイテムには自動的にIDが割り当てられます。",
    tags=["items"],
    operation_id="create_item",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "アイテムの作成に成功",
            "model": Item
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "無効なリクエストデータ",
            "model": ErrorResponse
        }
    }
)
async def create_item(
    item: ItemCreate = Body(
        ...,
        description="作成するアイテムの情報",
        example={
            "name": "ヘッドフォン",
            "description": "ノイズキャンセリング機能付きワイヤレスヘッドフォン",
            "price": 25000,
            "tags": ["電子機器", "オーディオ"]
        }
    )
):
    """
    新しいアイテムを作成します。
    
    提供されたデータを使用して新しいアイテムをデータベースに作成します。
    新しいアイテムIDは自動的に生成されます（既存の最大ID + 1）。
    """
    # 新しいIDを生成 (既存の最大ID + 1)
    new_id = max(items_db.keys(), default=0) + 1
    
    # アイテムを作成
    new_item = Item(
        id=new_id,
        name=item.name,
        description=item.description,
        price=item.price,
        tags=item.tags
    )
    
    # データベースに保存
    items_db[new_id] = new_item
    
    return new_item


@app.put(
    "/items/{item_id}",
    response_model=Item,
    summary="アイテム更新",
    description="指定されたIDのアイテム情報を更新します。リクエストで指定されたフィールドのみが更新されます。",
    tags=["items"],
    operation_id="update_item",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "アイテムの更新に成功",
            "model": Item
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "指定されたIDのアイテムが見つからない",
            "model": ErrorResponse
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "無効なリクエストデータ",
            "model": ErrorResponse
        }
    }
)
async def update_item(
    item_id: int = Path(
        ..., 
        description="更新するアイテムのID", 
        example=1,
        gt=0,
        title="アイテムID"
    ),
    item_update: ItemUpdate = Body(
        ...,
        description="更新するアイテムのデータ（更新したいフィールドのみ）",
        example={
            "price": 28000,
            "tags": ["電子機器", "オーディオ", "Bluetooth"]
        }
    )
):
    """
    既存のアイテムを更新します。
    
    指定されたIDのアイテムを、リクエストで提供されたデータで更新します。
    リクエストには、更新したいフィールドのみを含めることができます。
    指定されていないフィールドは変更されません。
    """
    # アイテムが存在するか確認
    if item_id not in items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Item not found"
        )
    
    # 既存のアイテムを取得
    existing_item = items_db[item_id]
    
    # 更新データを辞書に変換して非Noneの値のみを抽出
    update_data = {k: v for k, v in item_update.dict().items() if v is not None}
    
    # 更新データが空の場合
    if not update_data:
        return existing_item
    
    # 既存のアイテムデータを辞書に変換
    existing_item_dict = existing_item.dict()
    
    # 更新データで既存データを更新
    existing_item_dict.update(update_data)
    
    # 更新されたデータで新しいItemオブジェクトを作成
    updated_item = Item(**existing_item_dict)
    
    # データベースを更新
    items_db[item_id] = updated_item
    
    return updated_item


@app.delete(
    "/items/{item_id}",
    response_model=DeleteResponse,
    summary="アイテム削除",
    description="指定されたIDのアイテムをデータベースから削除します。",
    tags=["items"],
    operation_id="delete_item",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "アイテムの削除に成功",
            "model": DeleteResponse
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "指定されたIDのアイテムが見つからない",
            "model": ErrorResponse
        }
    }
)
async def delete_item(
    item_id: int = Path(
        ..., 
        description="削除するアイテムのID", 
        example=1,
        gt=0,
        title="アイテムID"
    )
):
    """
    アイテムを削除します。
    
    指定されたIDのアイテムをデータベースから完全に削除します。
    削除されたアイテムの情報、成功メッセージを含むレスポンスを返します。
    """
    # アイテムが存在するか確認
    if item_id not in items_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Item not found"
        )
    
    # アイテムを削除
    deleted_item = items_db.pop(item_id)
    
    return DeleteResponse(
        status="success",
        message=f"Item {item_id} deleted successfully",
        deleted_item=deleted_item
    )

# Create the MCP server
mcp = FastApiMCP(app)
mcp.mount()  # Mount the MCP server to the FastAPI app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simple_server:app", host="0.0.0.0", port=8888, reload=True)