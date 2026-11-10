"""
"agora" do sistema, no fuso horario do usuario (padrao: Brasilia)

o servidor guardava as datas em UTC, entao uma compra feita as 22h30 do dia 31 caia no mes seguinte
(UTC ja e dia 1). tudo que depende de "que dia/mes e hoje" usa estas funcoes.
prazos de seguranca (validade de link de senha, token) continuam em UTC, porque nao dependem do calendario

para outro fuso: FUSO_HORARIO=America/Manaus no .env
"""
import os
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _FUSO = ZoneInfo(os.getenv("FUSO_HORARIO", "America/Sao_Paulo"))
except Exception:
    # sem o pacote tzdata (comum no Windows) ou fuso invalido: horario de Brasilia fixo (sem horario de verao desde 2019)
    _FUSO = timezone(timedelta(hours=-3))


def agora():
    """data e hora de agora, no fuso do usuario, sem informacao de fuso (como o banco guarda)"""
    return datetime.now(_FUSO).replace(tzinfo=None)


def hoje():
    """hoje a meia-noite"""
    return agora().replace(hour=0, minute=0, second=0, microsecond=0)


def mes_atual():
    """'AAAA-MM' do mes atual"""
    return agora().strftime("%Y-%m")
