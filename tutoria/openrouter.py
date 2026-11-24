"""API HTTP do OpenRouter. Sem SDK, agentes, ferramentas ou retries de geração."""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .types import ModelCaps, TutorError

BASE_URL = "https://openrouter.ai/api/v1"


def api_error(code: int) -> TutorError:
    messages = {
        400: "O OpenRouter rejeitou os parâmetros ou a janela de contexto. Confira o modelo, reduza k/teto de saída ou encurte a conversa enviada.",
        401: "Chave OpenRouter inválida ou ausente. Confira a variável de ambiente ou o campo protegido.",
        402: "Saldo ou limite de crédito insuficiente no OpenRouter.",
        403: "O OpenRouter/provedor recusou a solicitação. Confira as restrições da conta e do modelo.",
        404: "Modelo ou rota não disponível no OpenRouter. Confira o identificador no catálogo.",
        408: "A chamada ao OpenRouter expirou. Tente novamente.",
        413: "A solicitação excedeu o limite do provedor. Reduza o contexto.",
        422: "O provedor não aceitou a configuração. Confira o modelo e os parâmetros.",
        429: "Limite de requisições atingido. Aguarde e tente novamente.",
        502: "O provedor do modelo está indisponível. Tente novamente ou selecione outro modelo.",
        503: "Nenhum provedor compatível está disponível. Tente outro modelo.",
    }
    return TutorError(messages.get(code, f"Falha na API OpenRouter (HTTP {code}). Tente novamente mais tarde."))


class OpenRouter:
    def __init__(self, api_key: str):
        if not api_key.strip():
            raise TutorError("Informe a chave do OpenRouter na barra lateral ou em OPENROUTER_API_KEY.")
        self._api_key = api_key.strip()

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        request = Request(
            BASE_URL + path, method=method,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
            headers={"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json", "X-OpenRouter-Title": "TutorIA local"},
        )
        try:
            with urlopen(request, timeout=90 if method == "POST" else 20) as response:
                data = json.load(response)
        except HTTPError as error:
            # Não exibimos corpo/headers: a API pode ecoar partes da solicitação.
            raise api_error(error.code) from None
        except (URLError, TimeoutError, socket.timeout):
            raise TutorError("Não foi possível confirmar a resposta do OpenRouter. Confira a conexão e tente novamente; a chamada anterior pode ter sido processada.") from None
        except (ValueError, OSError):
            raise TutorError("Resposta HTTP inválida do OpenRouter. Tente novamente.") from None
        if not isinstance(data, dict):
            raise TutorError("Formato de resposta inesperado do OpenRouter.")
        if "error" in data:
            try:
                code = int(data["error"].get("code", 500))
            except (ValueError, TypeError, AttributeError):
                code = 500
            raise api_error(code)
        return data

    def models(self) -> list[dict]:
        data = self._request("GET", "/models")
        if not isinstance(data.get("data"), list):
            raise TutorError("O catálogo de modelos retornou um formato inesperado.")
        return data["data"]

    def capabilities(self, model_id: str) -> ModelCaps:
        model = next((m for m in self.models() if m.get("id") == model_id), None)
        if model is None:
            raise TutorError("O identificador não foi encontrado no catálogo atual do OpenRouter. Confira o nome completo do modelo.")
        architecture = model.get("architecture") or {}
        if "text" not in architecture.get("input_modalities", []) or "text" not in architecture.get("output_modalities", []):
            raise TutorError("Escolha um modelo com entrada e saída de texto.")
        top = model.get("top_provider") or {}
        windows = [v for v in (model.get("context_length"), top.get("context_length")) if isinstance(v, int) and v > 0]
        if not windows:
            raise TutorError("O catálogo não informou a janela deste modelo. Selecione outro modelo.")
        maximum = top.get("max_completion_tokens")
        params = tuple(model.get("supported_parameters") or [])
        if "max_tokens" not in params:
            raise TutorError("O catálogo não confirma suporte ao teto max_tokens para este modelo. Escolha um modelo compatível.")
        return ModelCaps(model_id, min(windows), maximum if isinstance(maximum, int) and maximum > 0 else None, params)

    def complete(self, caps: ModelCaps, plan, temperature: float) -> dict:
        payload = {
            "model": caps.id, "messages": plan.messages, "max_tokens": plan.output_tokens,
            "stream": False, "provider": {"require_parameters": True},
            # Impede compactação automática de contexto que prejudicaria a trilha.
            "plugins": [{"id": "context-compression", "enabled": False}],
        }
        if "temperature" in caps.parameters:
            payload["temperature"] = temperature
        response = self._request("POST", "/chat/completions", payload)
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty content")
        except (KeyError, IndexError, TypeError, ValueError):
            raise TutorError("O modelo não retornou texto. Em modelos de raciocínio, o teto pode ter sido consumido antes da resposta; aumente-o ou selecione outro modelo.") from None
        return {"content": content, "finish_reason": choice.get("finish_reason"),
                "usage": response.get("usage", {}), "request_id": response.get("id"),
                "resolved_model": response.get("model", caps.id)}
