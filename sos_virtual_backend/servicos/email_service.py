"""
envio de e-mails do sistema (redefinicao de senha)

- com SMTP configurado no .env (SMTP_HOST etc.), o e-mail sai de verdade
- sem SMTP, entra em MODO DESENVOLVIMENTO: o e-mail aparece no terminal do servidor.
  serve para testar na propria maquina; em uso real configure o SMTP
- o envio roda em segundo plano: assim a resposta da API demora o mesmo tempo exista o e-mail
  ou nao (ninguem descobre quais e-mails estao cadastrados) e um SMTP lento nao trava a requisicao
"""
import logging
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage

log = logging.getLogger(__name__)


def _enviar(destino, assunto, corpo):
    host = os.getenv("SMTP_HOST", "").strip()

    if not host:
        print(
            "\n" + "=" * 64
            + "\n[MODO DESENVOLVIMENTO: SMTP nao configurado, nenhum e-mail foi enviado]"
            + f"\nPara: {destino}\nAssunto: {assunto}\n\n{corpo}\n"
            + "=" * 64 + "\n",
            flush=True,
        )
        return

    usuario = os.getenv("SMTP_USER", "").strip()
    senha = os.getenv("SMTP_PASSWORD", "")
    remetente = os.getenv("SMTP_FROM", "").strip() or usuario
    if not remetente:
        log.error("SMTP_FROM ou SMTP_USER precisa estar definido no .env")
        return

    try:
        porta = int(os.getenv("SMTP_PORT", "587"))

        # EmailMessage recusa quebras de linha nos cabecalhos (protege contra injecao de cabecalho)
        msg = EmailMessage()
        msg["Subject"] = assunto
        msg["From"] = remetente
        msg["To"] = destino
        msg.set_content(corpo)

        contexto = ssl.create_default_context()
        if porta == 465:
            servidor = smtplib.SMTP_SSL(host, porta, timeout=15, context=contexto)
        else:
            servidor = smtplib.SMTP(host, porta, timeout=15)
        with servidor:
            if porta != 465:
                servidor.starttls(context=contexto)  # nunca manda a senha sem criptografia
            if usuario:
                servidor.login(usuario, senha)
            servidor.send_message(msg)
    except Exception:
        # o erro fica so no log do servidor; mostrar ao usuario revelaria se o e-mail existe
        log.exception("falha ao enviar e-mail")


def _em_segundo_plano(destino, assunto, corpo):
    threading.Thread(
        target=_enviar, args=(destino, assunto, corpo), name="email-envio", daemon=True
    ).start()


def enviar_email_redefinicao(destino, nome, link, minutos):
    corpo = (
        f"Olá, {nome}!\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no SOS Virtual.\n"
        f"Para criar uma nova senha, abra o link abaixo. Ele vale por {minutos} minutos "
        "e só pode ser usado uma vez:\n\n"
        f"{link}\n\n"
        "Se você não fez esse pedido, ignore este e-mail: sua senha continua a mesma.\n\n"
        "— SOS Virtual"
    )
    _em_segundo_plano(destino, "SOS Virtual: redefinição de senha", corpo)


def enviar_email_senha_alterada(destino, nome):
    corpo = (
        f"Olá, {nome}!\n\n"
        "A senha da sua conta no SOS Virtual acabou de ser alterada.\n\n"
        "Se foi você, não precisa fazer nada. Se não foi, peça uma nova redefinição "
        "de senha imediatamente e fale com o responsável pelo sistema.\n\n"
        "— SOS Virtual"
    )
    _em_segundo_plano(destino, "SOS Virtual: sua senha foi alterada", corpo)
