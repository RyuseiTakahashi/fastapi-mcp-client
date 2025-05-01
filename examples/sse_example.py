"""
Interactive example for using FastAPI MCP Client with Item API and Claude.

This example allows you to query the Item API using natural language,
which gets interpreted by Claude API and executed against the FastAPI server.

Usage:
    python sse_example.py
"""

import asyncio
import json
import os
import signal
import sys
from typing import Dict, Any, List, Optional, Tuple
import httpx
from anthropic import Anthropic

from fastapi_mcp_client import MCPClient, MCPClientConfig
from dotenv import load_dotenv

# .envファイルのパスを指定して読み込み
dotenv_path = "/Users/ryuseitakahashi/Desktop/my_work/env/.env"
load_dotenv(dotenv_path)

def print_fancy_header(title: str):
    """Print a fancy header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


async def print_item(item: Dict[str, Any]):
    """
    Pretty print an item.
    
    Args:
        item: Item data
    """
    print(f"\n📦 Item #{item['id']}: {item['name']}")
    print(f"   💰 価格: ¥{item['price']:,}")
    
    if item.get('description'):
        print(f"   📝 説明: {item['description']}")
    
    if item.get('tags') and len(item['tags']) > 0:
        print(f"   🏷️ タグ: {', '.join(item['tags'])}")


openapi_schema = {}
async def fetch_available_tools(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """
    FastAPI サーバーから利用可能なツール情報を取得します。
    
    Args:
        client: HTTP クライアント
        
    Returns:
        利用可能なツールのリスト
    """
    global openapi_schema  # グローバル変数を使用宣言

    print("🔍 APIからツール情報を取得しています...")
    try:
        # FastAPI の OpenAPI スキーマを取得。OpenAPI スキーマは API のエンドポイント、パラメータ、レスポンスなどのメタデータを含む
        response = await client.get("/openapi.json")
        # ステータスコードが 400 以上の場合は例外をスロー
        response.raise_for_status()
        
        # レスポンスを JSON としてパース
        openapi_schema = response.json()
        
        tools = []
        
        # OpenAPI スキーマのパス情報をループして処理をする。各パスは "/items/" や "/items/{item_id}" などのエンドポイントが含まれる
        for path, path_info in openapi_schema.get("paths", {}).items():
            # 各パスの HTTP メソッドをループして処理をする。GET や POST などのメソッドが含まれており、operationId が存在する場合はツールとして処理する
            for method, operation in path_info.items():
                # operationId が存在しない場合はスキップし処理を行わない
                if "operationId" not in operation:
                    continue
                
                operation_id = operation["operationId"]
                
                properties = {}
                required = []
                
                # パスパラメータを抽出 (例: /items/{item_id} の item_id)
                for param in operation.get("parameters", []):
                    # パスパラメータのみを処理 (クエリパラメータなどは除外)
                    if param.get("in") == "path":
                        param_name = param.get("name", "")
                        param_schema = param.get("schema", {})
                        param_required = param.get("required", False)
                        
                        # パラメータの型情報を properties に追加
                        properties[param_name] = {
                            "type": param_schema.get("type", "string"),
                            "description": param.get("description", f"Parameter {param_name}")
                        }
                        
                        # 必須パラメータの場合は required リストに追加
                        if param_required:
                            required.append(param_name)
                
                # リクエストボディのスキーマがある場合 (POST, PUT メソッドなど)
                if "requestBody" in operation:
                    # application/json コンテンツタイプのスキーマを取得
                    content = operation["requestBody"].get("content", {})
                    json_schema = content.get("application/json", {}).get("schema", {})
                    
                    # リクエストボディのプロパティを処理
                    if "properties" in json_schema:
                        for prop_name, prop_schema in json_schema["properties"].items():
                            properties[prop_name] = {
                                "type": prop_schema.get("type", "string"),
                                "description": prop_schema.get("description", f"Property {prop_name}")
                            }
                        
                        # リクエストボディの必須プロパティを required リストに追加
                        if "required" in json_schema:
                            required.extend(json_schema["required"])

                # ツール定義を作成。Claude API の tools パラメータで使用される形式に合わせる
                tool = {
                    "name": operation_id,
                    "description": operation.get("summary", "") or operation.get("description", "") or f"Call {operation_id}",
                    "input_schema": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
                
                tools.append(tool)
        
        print(f"✅ {len(tools)}個のツールを検出しました")
        return tools
        
    except Exception as e:
        print(f"❌ ツール情報の取得に失敗しました: {str(e)}")
        return []


async def process_query_with_claude(query: str, anthropic_client: Anthropic, 
                                   mcp_client: MCPClient, available_tools: List[Dict[str, Any]]) -> str:
    """
    Claude AIを使用してクエリを処理し、必要に応じてツール呼び出しを実行します。
    
    Args:
        query: ユーザーからの自然言語クエリ
        anthropic_client: Anthropic Claude APIクライアント
        mcp_client: MCPクライアント（APIリクエスト実行用）
        available_tools: 利用可能なAPIツールのリスト
        
    Returns:
        最終的な応答テキスト
    """
    global openapi_schema  # グローバル変数を使用

    system_prompt = f"""
    あなたはFastAPIサーバーにリクエストを行うアシスタントです。
    ユーザーが自然言語で商品検索についての要求を出します。
    あなたはユーザーの意図を解釈し、適切なAPIエンドポイントを選択し、必要なパラメータを設定してください。
    利用可能なAPIエンドポイントは自動的に検出され、ツールとして提供されています。
    必要に応じて適切なツールを選択して応答してください。
    
    ユーザーの要求: {query}
    """

    # Claudeに送信するメッセージを構造化データとして構築
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": system_prompt
                }
            ]
        }
    ]
    
    print("🤖 Claudeに分析を依頼しています...")
    
    # Process response and handle tool calls
    final_text = []
    
    try:
        # Claude APIを呼び出し、ユーザークエリの解析を依頼
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages,
            tools=available_tools
        )
        
        assistant_message_content = []
        
        # Claudeからの各コンテンツ要素（テキストまたはツール使用）を処理
        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
                assistant_message_content.append(content)
                
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input

                print("-" * 50)
                print(content)
                
                print(f"🧠 Claude解析結果: '{tool_name}' ツールを呼び出すことに決定しました")
                print(f"   パラメータ: {json.dumps(tool_args, ensure_ascii=False)}")
                
                result = None
                # OpenAPIスキーマを使用した動的エンドポイント構築
                try:
                    # OpenAPIスキーマからツール名に対応するパスと操作を検索
                    operation_info = None
                    endpoint_path = None
                    http_method = None
                    
                    # OpenAPIスキーマからツールに対応するエンドポイント情報を検索
                    for path, path_info in openapi_schema.get("paths", {}).items():
                        for method, operation in path_info.items():
                            if operation.get("operationId") == tool_name:
                                operation_info = operation
                                endpoint_path = path
                                http_method = method.upper()
                                break
                        if operation_info:
                            break
                    
                    print(f"🔍 エンドポイント検索結果: パス={endpoint_path}, メソッド={http_method}")
                    
                    # エンドポイント情報が見つかった場合、リクエストを実行
                    if endpoint_path and http_method:
                        # パスパラメータを置換
                        formatted_path = endpoint_path
                        for param in operation_info.get("parameters", []):
                            # パスパラメータのみを処理
                            if param.get("in") == "path":
                                param_name = param.get("name")
                                if param_name in tool_args:
                                    param_value = str(tool_args[param_name])
                                    formatted_path = formatted_path.replace(f"{{{param_name}}}", param_value)
                                    print(f"   パスパラメータ置換: {{{param_name}}} → {param_value}")
                        
                        print(f"📡 APIリクエスト: {http_method} {formatted_path}")
                        
                        # リクエスト実行
                        if http_method == "GET":
                            # 非パスパラメータがあればクエリパラメータとして使用
                            query_params = {}
                            for key, value in tool_args.items():
                                if f"{{{key}}}" not in endpoint_path:
                                    query_params[key] = value
                            
                            response = await mcp_client._async_client.get(formatted_path, params=query_params)
                        elif http_method == "POST":
                            response = await mcp_client._async_client.post(formatted_path, json=tool_args)
                        elif http_method == "PUT":
                            response = await mcp_client._async_client.put(formatted_path, json={"item_id":1, "price":1})
                        elif http_method == "DELETE":
                            response = await mcp_client._async_client.delete(formatted_path)
                            
                        # レスポンス処理
                        if response.status_code == 404:
                            result = {"error": "Resource not found", "status_code": 404}
                        else:
                            response.raise_for_status()
                            if response.status_code != 204:  # No Content
                                result = response.json()
                            else:
                                result = {"status": "success", "status_code": 204}
                    else:
                        # スキーマに情報がない場合のフォールバック
                        print("⚠️ OpenAPIスキーマにツール情報が見つかりません。")
                        print("ツール名:", tool_name)
                        print("ツール引数:", tool_args)
                        print("ツール情報を取得できませんでした。")
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ API実行エラー: {error_msg}")
                    result = {"error": f"API call failed: {error_msg}"}
                # ========== ここまで変更 ==========
                
                # ツール実行結果をJSON文字列に変換
                result_str = json.dumps(result, ensure_ascii=False, indent=2)
                final_text.append(f"\n[ツール {tool_name} を実行しました]\n結果:\n{result_str}\n")
                
                # Claudeとの会話を継続
                assistant_message_content.append(content)
                messages.append({
                    "role": "assistant",
                    "content": assistant_message_content
                })
                
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": content.id,
                            "content": result_str
                        }
                    ]
                })
                
                # ツール実行結果をClaudeに送信
                print("🤖 ツール実行結果をClaudeに送信しています...")
                
                response = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=messages,
                    tools=available_tools
                )
                
                # 最終回答を追加
                if response.content and response.content[0].type == 'text':
                    final_text.append(response.content[0].text)
        
        # 最終的な応答を返す
        return "\n".join(final_text)
        
    except Exception as e:
        print(f"❌ Claudeとの会話中にエラーが発生しました: {str(e)}")
        return f"エラーが発生しました: {str(e)}"

async def execute_api_based_on_claude(query: str, anthropic_client: Anthropic, mcp_client: MCPClient) -> Any:
    """
    Use Claude to interpret the query and execute the appropriate API call.
    
    Args:
        query: The natural language query
        anthropic_client: The Anthropic Claude client
        mcp_client: The MCP client
        
    Returns:
        API response
    """
    try:
        # Fetch available tools from the server
        available_tools = await fetch_available_tools(mcp_client._async_client)
        
        # Process the query with Claude
        response_text = await process_query_with_claude(query, anthropic_client, mcp_client, available_tools)
        
        # Display Claude's analysis
        print("\n🧠 Claudeの分析と実行結果:")
        print("-" * 50)
        print(response_text)
        print("-" * 50)
        
        # The API call was executed inside process_query_with_claude
        # Return a success message
        return {"success": True, "claude_response": response_text}
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {str(e)}")
        return {"error": str(e)}


async def interactive_client(api_url: str):
    """
    Interactive client that accepts natural language queries.
    
    Args:
        api_url: The URL of the API
    """
    # Get API key from environment variable
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEYが環境変数に設定されていません。")
        print("   export ANTHROPIC_API_KEY=your_api_key を実行してください。")
        return
        
    # Create Anthropic client
    anthropic_client = Anthropic(api_key=api_key)
    
    # Create client configuration
    config = MCPClientConfig(
        base_url=api_url,
        timeout=30.0,
        log_level="INFO",
        client_info={"name": "Interactive FastAPI MCP Client", "version": "0.1.0"},
    )
    
    # Create client
    async with MCPClient(api_url, config=config) as client:
        print_fancy_header("FastAPI MCP Interactive Client (Powered by Claude)")
        print(f"接続先: {api_url}")
        print("終了するには「終了」「exit」「quit」と入力してください")
        print("商品を検索するには「全ての商品を表示して」「IDが2の商品を表示して」などと入力してください")
        print("-" * 70)

        # 起動時にOpenAPIスキーマを取得
        tools = await fetch_available_tools(client._async_client)
        print(f"利用可能なツール: {', '.join([tool['name'] for tool in tools])}")
        print("-" * 70)
        
        while True:
            try:
                # Get user query
                query = input("\n🔍 クエリを入力してください: ")
                
                # Check for exit command
                if query.lower() in ["終了", "exit", "quit", "q"]:
                    print("👋 プログラムを終了します")
                    break
                    
                if not query.strip():
                    continue
                
                # Use Claude to interpret and execute the query
                await execute_api_based_on_claude(query, anthropic_client, client)
                
            except KeyboardInterrupt:
                print("\n👋 プログラムを終了します")
                break
                
            except Exception as e:
                print(f"❌ エラーが発生しました: {str(e)}")


def setup_signal_handlers():
    """Set up clean shutdown on CTRL+C."""
    def handle_sigint(*args):
        print("\n👋 プログラムを終了します")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)


if __name__ == "__main__":
    # Set up signal handlers
    setup_signal_handlers()
    
    # Get API URL from environment or use default
    api_url = os.environ.get("API_URL", "http://localhost:8888")
    
    # Print startup information
    print("=" * 70)
    print("FastAPI MCP インタラクティブクライアント (Powered by Claude)")
    print("=" * 70)
    print("自然言語でAPIにクエリを送信できます。Claudeがクエリを解釈します。")
    print("\nこのプログラムを実行する前に、以下を確認してください:")
    print("  1. サーバーが起動している (python simple_server.py)")
    print("  2. ANTHROPIC_API_KEY環境変数が設定されている")
    print(f"\nサーバー接続先: {api_url}")
    print("(API_URL環境変数で変更可能)")
    print("=" * 70)
    
    # Run the interactive client
    asyncio.run(interactive_client(api_url))