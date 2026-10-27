import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Tuple, Any

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modelos gratuitos populares e recomendados no OpenRouter
FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
]


def clean_json_response(raw_content: str) -> str:
    """Remove blocos de código markdown (```json ... ```) se presentes na resposta do modelo."""
    raw = raw_content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        return match.group(1).strip()
    return raw


def call_openrouter(
    prompt: str,
    system_prompt: str,
    api_key: str,
    model: str = "meta-llama/llama-3.3-70b-instruct:free",
    temperature: float = 0.7,
    max_tokens: int = 1500,
    timeout: int = 35,
) -> str:
    """
    Executa uma requisição direta ao OpenRouter usando apenas bibliotecas nativas (urllib).
    Retorna o texto da resposta ou levanta RuntimeError com mensagem legível.
    """
    if not api_key or not api_key.strip():
        raise ValueError("Chave de API do OpenRouter não configurada. Configure em '⚙️ Configurar IA'.")

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/whatsapp-template-generator",
        "X-Title": "WhatsApp Template Generator",
    }

    payload = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OPENROUTER_URL, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            resp_body = response.read().decode("utf-8")

            if status != 200:
                raise RuntimeError(f"Erro HTTP {status}: {resp_body}")

            result_json = json.loads(resp_body)
            choices = result_json.get("choices", [])
            if not choices:
                raise RuntimeError("Resposta vazia da API do OpenRouter.")

            content = choices[0].get("message", {}).get("content", "")
            return content.strip()

    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8", errors="replace")
        try:
            parsed_err = json.loads(error_msg)
            if "error" in parsed_err and "message" in parsed_err["error"]:
                error_msg = parsed_err["error"]["message"]
        except Exception:
            pass

        if e.code == 401:
            raise RuntimeError("Chave de API inválida ou não autorizada no OpenRouter.") from e
        elif e.code == 402:
            raise RuntimeError("Limite ou créditos insuficientes na conta OpenRouter.") from e
        elif e.code == 429:
            raise RuntimeError("Muitas requisições (Rate limit) no modelo gratuito. Aguarde alguns instantes.") from e
        else:
            raise RuntimeError(f"Erro na API OpenRouter ({e.code}): {error_msg}") from e

    except urllib.error.URLError as e:
        raise RuntimeError(f"Erro de conexão com OpenRouter: {e.reason}. Verifique sua internet.") from e
    except TimeoutError:
        raise RuntimeError("Tempo limite de resposta excedido. O modelo demorou para responder.")


def test_api_connection(api_key: str, model: str) -> Tuple[bool, str]:
    """Testa se a API Key e o modelo configurados estão funcionando."""
    try:
        resp = call_openrouter(
            prompt="Diga apenas 'OK' em uma palavra para confirmar a conexao.",
            system_prompt="Você é um assistente de teste de conexão. Responda apenas 'OK'.",
            api_key=api_key,
            model=model,
            max_tokens=10,
            timeout=15,
        )
        return True, f"Conexão estabelecida com sucesso com o modelo '{model}'!"
    except Exception as e:
        return False, str(e)


def extract_variables_from_context(
    raw_context: str,
    template_text: str,
    campos: List[str],
    api_key: str,
    model: str,
) -> Dict[str, str]:
    """
    Papel 1: Smart Auto-Fill.
    Lê o contexto bruto fornecido pelo usuário e preenche as variáveis do template.
    Retorna um dicionário {campo: valor}.
    """
    system_prompt = (
        "Você é um assistente de inteligência artificial especializado em extração de informações para WhatsApp.\n"
        "Sua tarefa é analisar o texto desestruturado fornecido pelo usuário e extrair os valores correspondentes "
        "aos campos solicitados.\n"
        "Regras estritas:\n"
        "1. Retorne ESTRITAMENTE um objeto JSON válido, sem comentários, sem explicações e sem blocos markdown.\n"
        "2. As chaves do JSON DEVEM ser exatamente os nomes dos campos solicitados.\n"
        "3. Se uma informação não for encontrada no texto, use uma string vazia \"\" para aquele campo.\n"
        "4. Formate datas, valores e horários de forma limpa e adequada para mensagens em português (ex: R$ 150,00, 28/10 às 14h)."
    )

    campos_formatados = ", ".join([f'"{c}"' for c in campos])
    user_prompt = (
        f"Campos necessários:\n[{campos_formatados}]\n\n"
        f"Template de Mensagem de Destino:\n{template_text}\n\n"
        f"Texto bruto / Conversa com os dados:\n\"\"\"\n{raw_context}\n\"\"\"\n\n"
        f"Extraia os dados do texto acima e responda SOMENTE com o JSON correspondente."
    )

    response_text = call_openrouter(
        prompt=user_prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
        temperature=0.2,  # Baixa temperatura para precisão factual
    )

    cleaned = clean_json_response(response_text)
    try:
        extracted = json.loads(cleaned)
        if isinstance(extracted, dict):
            # Garante que todos os campos solicitados existam no resultado
            return {c: str(extracted.get(c, "")).strip() for c in campos}
        return {}
    except json.JSONDecodeError:
        # Fallback via regex simples caso o modelo tenha retornado algo quase-JSON
        result = {}
        for c in campos:
            m = re.search(rf'"{c}"\s*:\s*"([^"]*)"', cleaned)
            if m:
                result[c] = m.group(1).strip()
            else:
                result[c] = ""
        return result


def adapt_message_tone(
    message_text: str,
    target_tone: str,
    api_key: str,
    model: str,
) -> str:
    """
    Papel 2: Tone & Style Switcher.
    Reescreve a mensagem no tom desejado mantendo informações factuais e formatação do WhatsApp (*negrito*, etc.).
    """
    tone_instructions = {
        "formal": "Reescreva a mensagem com um tom profissional, corporativo, polido e respeitoso.",
        "amigavel": "Reescreva a mensagem com um tom caloroso, simpático, amigável e acolhedor.",
        "cobranca_suave": "Reescreva a mensagem como um lembrete delicado, empático e prestativo, evitando qualquer tom agressivo.",
        "direto": "Reescreva a mensagem de forma ultra concisa, direta ao ponto e sem rodeios, ideal para leitura rápida.",
    }

    specific_instruction = tone_instructions.get(target_tone, f"Reescreva a mensagem no tom: {target_tone}.")

    system_prompt = (
        "Você é um redator especialista em comunicação para WhatsApp.\n"
        "Sua missão é adaptar o estilo e tom da mensagem fornecida pelo usuário, seguindo as diretrizes:\n"
        "1. Mantenha TODAS as informações factuais intactas (nomes, valores, datas, chaves pix, links, prazos).\n"
        "2. Preserve ou aplique formatação compatível com WhatsApp (*negrito* para pontos chave, `código` para chaves pix ou senhas).\n"
        "3. Não invente novos fatos ou promessas que não estavam na mensagem original.\n"
        "4. Responda APENAS com o texto final pronto para ser enviado no WhatsApp, sem saudações com o usuário e sem comentários sobre a alteração."
    )

    user_prompt = (
        f"Instrução de Tom: {specific_instruction}\n\n"
        f"Mensagem original:\n\"\"\"\n{message_text}\n\"\"\"\n\n"
        f"Forneça apenas a mensagem adaptada:"
    )

    return call_openrouter(
        prompt=user_prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
        temperature=0.6,
    )


def generate_template_from_prompt(
    user_prompt_desc: str,
    api_key: str,
    model: str,
) -> Dict[str, Any]:
    """
    Papel 3: Gerador Mágico de Novos Templates.
    Gera um novo template a partir de uma breve descrição dada pelo usuário.
    Retorna dict com 'titulo', 'template' e 'campos'.
    """
    system_prompt = (
        "Você é um arquiteto especialista em criar templates de mensagens para WhatsApp comercial.\n"
        "Ao receber uma solicitação do usuário, crie um template estruturado e profissional.\n"
        "Regras obrigatórias:\n"
        "1. Identifique as partes que devem ser variáveis e insira-as entre chaves simples {nome_da_variavel} "
        "(exemplo: {cliente}, {servico}, {data}, {valor}, {pix}).\n"
        "2. Utilize formatação nativa do WhatsApp: *negrito* para destaques, _itálico_ e `código` quando relevante.\n"
        "3. Retorne ESTRITAMENTE um JSON com as seguintes chaves:\n"
        "   - 'titulo': Um título descritivo curto para o modelo.\n"
        "   - 'template': O corpo completo da mensagem com os placeholders entre chaves.\n"
        "   - 'campos': Lista contendo os nomes das variáveis utilizadas.\n"
        "4. NÃO inclua nenhum texto ou explicação fora do JSON."
    )

    user_prompt = (
        f"Crie um template de mensagem para WhatsApp com base nesta descrição:\n"
        f"\"{user_prompt_desc}\"\n\n"
        f"Responda apenas com o JSON estruturado."
    )

    response_text = call_openrouter(
        prompt=user_prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
        temperature=0.7,
    )

    cleaned = clean_json_response(response_text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "titulo" in data and "template" in data:
            # Re-extrai placeholders para garantir consistência
            template_body = data.get("template", "")
            matches = re.findall(r"\{([a-zA-Z0-9_]+)\}", template_body)
            campos = list(dict.fromkeys(matches))
            return {
                "titulo": str(data.get("titulo", "Novo Modelo")).strip(),
                "template": template_body.strip(),
                "campos": campos,
            }
    except Exception:
        pass

    raise RuntimeError("A IA não retornou o formato JSON esperado para o novo template. Tente descrever com mais detalhes.")


def detect_and_parametrize_variables(
    raw_message_text: str,
    api_key: str,
    model: str,
) -> Dict[str, Any]:
    """
    Analisa um texto de mensagem comum e identifica partes que devem ser variáveis,
    substituindo-as por tags padronizadas entre chaves {nome_da_variavel}.
    Retorna dict com 'template', 'campos' e 'titulo_sugerido'.
    """
    system_prompt = (
        "Você é um especialista em parametrização de templates de mensagens para WhatsApp comercial.\n"
        "Ao receber uma mensagem de exemplo (com dados fictícios ou reais digitados pelo usuário), sua tarefa é "
        "identificar todos os trechos que devem se tornar variáveis preenchíveis dinamicamente.\n\n"
        "Regras obrigatórias:\n"
        "1. Substitua dados específicos (nomes próprios, valores em dinheiro, datas, horários, prazos, chaves PIX, "
        "endereços, códigos, produtos ou serviços) por tags entre chaves simples {nome_da_variavel} em minúsculas "
        "sem acentos (exemplo: {cliente}, {servico}, {data}, {horario}, {valor}, {pix}, {endereco}).\n"
        "2. Se o texto já contiver variáveis entre chaves (como {cliente}), MANTENHA-AS e parametrize o restante.\n"
        "3. Preserve pontuação, quebras de linha e formatações de WhatsApp (*negrito*, etc.).\n"
        "4. Sugira um título profissional e curto para o template.\n"
        "5. Retorne ESTRITAMENTE um JSON válido com:\n"
        "   - 'template': O texto transformado com as chaves {variavel}.\n"
        "   - 'campos': Lista dos nomes das variáveis identificadas.\n"
        "   - 'titulo_sugerido': Título curto sugerido.\n"
        "6. NÃO inclua comentários ou texto fora do JSON."
    )

    user_prompt = (
        f"Analise o texto da mensagem abaixo e parametrize todas as variáveis:\n\"\"\"\n{raw_message_text}\n\"\"\"\n\n"
        f"Responda apenas com o JSON estruturado."
    )

    response_text = call_openrouter(
        prompt=user_prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
        temperature=0.3,  # Baixa temperatura para precisão
    )

    cleaned = clean_json_response(response_text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "template" in data:
            template_body = data.get("template", "")
            matches = re.findall(r"\{([a-zA-Z0-9_]+)\}", template_body)
            campos = list(dict.fromkeys(matches))
            return {
                "template": template_body.strip(),
                "campos": campos,
                "titulo_sugerido": str(data.get("titulo_sugerido", "Template Personalizado")).strip(),
            }
    except Exception:
        pass

    raise RuntimeError("A IA não retornou o formato JSON esperado para parametrização do template.")
