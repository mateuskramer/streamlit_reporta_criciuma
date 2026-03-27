import streamlit as st
from supabase import Client


def inicializar_sessao():
    """Garante que as chaves de sessão existem."""
    defaults = {
        "usuario_id":    None,
        "usuario_email": None,
        "usuario_nome":  None,
        "usuario_role":  None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def esta_logado() -> bool:
    return st.session_state.get("usuario_id") is not None


def e_admin() -> bool:
    return st.session_state.get("usuario_role") == "admin"


def fazer_login(supabase: Client, email: str, senha: str) -> str | None:
    """
    Tenta autenticar o usuário.
    Retorna None em caso de sucesso, ou uma mensagem de erro.
    """
    try:
        resp = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        user = resp.user
        if user is None:
            return "Email ou senha incorretos."

        # Busca o perfil para pegar nome e role
        perfil = (
            supabase.table("perfis")
            .select("nome, role")
            .eq("id", user.id)
            .single()
            .execute()
            .data
        )

        st.session_state["usuario_id"]    = user.id
        st.session_state["usuario_email"] = user.email
        st.session_state["usuario_nome"]  = perfil.get("nome", user.email)
        st.session_state["usuario_role"]  = perfil.get("role", "cidadao")
        return None

    except Exception as e:
        msg = str(e)
        if "Invalid login credentials" in msg:
            return "Email ou senha incorretos."
        return f"Erro ao fazer login: {msg[:80]}"


def fazer_logout(supabase: Client):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    for k in ["usuario_id", "usuario_email", "usuario_nome", "usuario_role"]:
        st.session_state[k] = None
    st.rerun()


def tela_login(supabase: Client):
    """Renderiza a tela de login centralizada."""
    col_esq, col_centro, col_dir = st.columns([1, 1.5, 1])
    with col_centro:
        st.image("https://img.icons8.com/fluency/96/city-buildings.png", width=80)
        st.title("Reporta Criciúma")
        st.caption("Faça login para reportar problemas na cidade.")
        st.markdown("---")

        with st.form("form_login"):
            email = st.text_input("Email", placeholder="seu@email.com")
            senha = st.text_input("Senha", type="password", placeholder="••••••••")
            entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)

            if entrar:
                if not email or not senha:
                    st.warning("Preencha email e senha.")
                else:
                    with st.spinner("Autenticando..."):
                        erro = fazer_login(supabase, email, senha)
                    if erro:
                        st.error(erro)
                    else:
                        st.rerun()


def sidebar_usuario(supabase: Client):
    """Mostra info do usuário logado e botão de logout na sidebar."""
    nome  = st.session_state.get("usuario_nome", "")
    email = st.session_state.get("usuario_email", "")
    role  = st.session_state.get("usuario_role", "cidadao")

    icone = "🔐" if role == "admin" else "👤"
    st.sidebar.markdown(f"**{icone} {nome}**")
    st.sidebar.caption(email)
    if st.sidebar.button("Sair", use_container_width=True):
        fazer_logout(supabase)
