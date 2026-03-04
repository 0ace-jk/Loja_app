import streamlit as st
import pandas as pd
import qrcode
from datetime import datetime
from pix_utils_ace import Code
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 1. PARÂMETROS DE NEGÓCIO
# ==========================================
TABELA_PRECOS = {
    'Padrao': st.secrets.valor.basica,
    'Especial': st.secrets.valor.especial,
    'Infantil': st.secrets.valor.infantil
}

CHAVE_PIX = st.secrets.variaveis.chave_pix_recebedor
NOME_RECEBEDOR = 'Loja Luz do Norte'
CIDADE_RECEBEDOR = 'MANAUS'

PRODUTOS = ['Camiseta Adulto', 'Camiseta Infantil']
CORES = ['Verde', 'Bege']
GRADE_PADRAO = ['PP', 'P', 'M', 'G', 'GG']
GRADE_ESPECIAL = ['G1', 'G3']
GRADE_INFANTIL = ['4', '6', '8', '10']

TODOS_SKUS = []
for cor in CORES:
    for tam in GRADE_PADRAO + GRADE_ESPECIAL:
        TODOS_SKUS.append(f'{cor}-{tam}')
    for tam in GRADE_INFANTIL:
        TODOS_SKUS.append(f'{cor}-Infantil-{tam}')

st.set_page_config(page_title="Lojinha do Norte", layout="centered")

# ==========================================
# 2. FUNÇÕES
# ==========================================

def calcular_valor_total(carrinho):
    """
    Motor financeiro: Lê o SKU e aplica o preço correto consultando a TABELA_PRECOS.
    """
    total = 0.0
    for sku, qtd in carrinho.items():
        if qtd > 0:
            if 'Infantil' in sku:
                total += (qtd * TABELA_PRECOS['Infantil'])
            elif any(tam in sku for tam in GRADE_ESPECIAL):
                total += (qtd * TABELA_PRECOS['Especial'])
            else:
                total += (qtd * TABELA_PRECOS['Padrao'])
    return total



conn = st.connection("gsheets", type=GSheetsConnection)
def gravar_pedido_wide(cliente, carrinho, valor_total):
    """
    Transforma o carrinho em uma linha de Formato Largo (Wide Form).
    """
    # 2. Inicia o registro com os metadados (Cabeçalho)
    registro = {
        "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "Nome": cliente['nome'],
        "WhatsApp": cliente['telefone']
    }
    # 3. Preenche TODO O ESTOQUE com zero (Garante a matriz perfeita)
    for sku in TODOS_SKUS:
        registro[sku] = 0
        
    # 4. Sobrescreve apenas o que foi comprado
    for sku_comprado, quantidade in carrinho.items():
        if sku_comprado in registro:
            registro[sku_comprado] = quantidade
            
    # 5. Adiciona os dados financeiros no final
    registro["Valor Total"] = valor_total
    registro["Status PIX"] = "Pendente"
    # Converte para DataFrame de uma única linha
    df_novo_pedido = pd.DataFrame([registro])
    
    try:
        # Lê a base atual e concatena
        df_atual = conn.read(worksheet="Pedidos", ttl=0)
        
        df_final = pd.concat([df_atual, df_novo_pedido], ignore_index=True)
        
        # Opcional, mas recomendado: forçar que espaços vazios da leitura virem 0 numérico
        df_final = df_final.fillna(0)
        
        # Atualiza a nuvem
        conn.update(worksheet="Pedidos", data=df_final)
        return True
    except Exception as e:
        # Em produção, logar o erro. No Streamlit, mostrar na tela.
        print(f"Erro no pipeline de gravação: {e}")
        return False

# ==========================================
# 3. LÓGICA DO PIX OFFLINE
# ==========================================
def gerar_codigo_pix(valor, identificador):
    pix_data = {
        'key': CHAVE_PIX,
        'name': NOME_RECEBEDOR,
        'city': CIDADE_RECEBEDOR,
        'value': valor,
        'identifier': identificador
    }
    payload = Code(**pix_data)
    return payload

# ==========================================
# 4. GESTÃO DE SESSÃO
# ==========================================
for key in ['etapa', 'carrinho', 'cliente', 'cod_pix', 'admin_logado']:
    if key not in st.session_state:
        st.session_state[key] = 1 if key == 'etapa' else {} if key in ['carrinho', 'cliente', 'cod_pix'] else False

# ==========================================
# 5. PAINEL DE ADMINISTRAÇÃO (SIDEBAR)
# ==========================================
with st.sidebar:
    st.subheader("⚙️ Operação")
    if not st.session_state.admin_logado:
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Acessar"):
            if usuario == st.secrets.admin_login.usuario and senha == st.secrets.admin_login.senha:
                st.session_state.admin_logado = True
                st.rerun()
            else:
                st.error("Acesso Negado.")
    else:
        st.success("Admin Logado")
        if st.button("Sair"):
            st.session_state.admin_logado = False
            st.rerun()

# ==========================================
# 6. INTERFACE PRINCIPAL
# ==========================================
# VISÃO DO ADMIN
if st.session_state.admin_logado:
    st.title("📋 Relatório da Operação")
    st.info("Para confirmar os pagamentos, abra a planilha no seu Google Sheets e altere a coluna 'Status PIX'.")
    try:
        df_pedidos = conn.read(worksheet="Pedidos", ttl=0)
        st.metric("Total Vendido", f"R$ {df_pedidos['Valor Total'].sum():.2f}")
        st.dataframe(df_pedidos, use_container_width=True)
    except Exception as e:
        st.warning("A planilha 'Pedidos' ainda está vazia ou inacessível.")
        
# VISÃO DO CLIENTE
else:
    if st.session_state.etapa == 1:
        st.title('🛒 Lojinha do Norte')
        st.info('Selecione as quantidades desejadas. Os valores totais serão calculados na próxima etapa.')

        with st.form('form_loja'):
            escolhas_temporarias = {}

# --- BLOCO 1: PADRÃO ---
            st.subheader(f"Adulto Padrão - R$ {TABELA_PRECOS['Padrao']:.2f}")
            for cor in CORES:
                st.markdown(f"**{cor}**")
                cols_padrao = st.columns(len(GRADE_PADRAO))
                for i, tam in enumerate(GRADE_PADRAO):
                    sku = f"{cor}-{tam}"
                    with cols_padrao[i]:
                        escolhas_temporarias[sku] = st.number_input(tam, min_value=0, step=1, key=f"padrao_{sku}")
            
            st.divider()
            
            # --- BLOCO 2: ESPECIAL ---
            st.subheader(f"Adulto Especial - R$ {TABELA_PRECOS['Especial']:.2f}")
            for cor in CORES:
                st.markdown(f"**{cor}**")
                cols_esp = st.columns(len(GRADE_ESPECIAL))
                for i, tam in enumerate(GRADE_ESPECIAL):
                    sku = f"{cor}-{tam}"
                    with cols_esp[i]:
                        escolhas_temporarias[sku] = st.number_input(tam, min_value=0, step=1, key=f"esp_{sku}")
            
            st.divider()
            
            # --- BLOCO 3: INFANTIL ---
            st.subheader(f"Linha Infantil - R$ {TABELA_PRECOS['Infantil']:.2f}")
            for cor in CORES:
                st.markdown(f"**{cor}**")
                cols_inf = st.columns(len(GRADE_INFANTIL))
                for i, tam in enumerate(GRADE_INFANTIL):
                    # Adiciona a tag 'Inf' no SKU para o banco de dados e motor de preço saberem o que é
                    sku = f"{cor}-Infantil-{tam}" 
                    with cols_inf[i]:
                        escolhas_temporarias[sku] = st.number_input(tam, min_value=0, step=1, key=f"inf_{sku}")
            
            st.divider()
            
            # --- DADOS DO CLIENTE E SUBMISSÃO ---
            st.subheader("Seus Dados")
            nome = st.text_input("Nome Completo")
            tel = st.text_input("WhatsApp (com DDD)")
            
            if st.form_submit_button("Avançar para Pagamento", type="primary"):
                # Filtra apenas os SKUs que tiveram pelo menos 1 unidade selecionada
                carrinho_valido = {sku: qtd for sku, qtd in escolhas_temporarias.items() if qtd > 0}
                
                if not carrinho_valido:
                    st.error("Adicione pelo menos um item ao carrinho.")
                elif not nome or not tel:
                    st.error("Preencha seu Nome e WhatsApp.")
                else:
                    # Salva no estado da sessão para a Etapa 2
                    st.session_state.carrinho = carrinho_valido
                    st.session_state.cliente = {'nome': nome, 'telefone': tel}
                    st.session_state.etapa = 2
                    st.rerun()

# --- ETAPA 2: CHECKOUT E PAGAMENTO ---
    elif st.session_state.etapa == 2:
        st.title('💸 Resumo e Pagamento')
        
        # 1. Processamento Financeiro
        valor_total = calcular_valor_total(st.session_state.carrinho)
        total_pecas = sum(st.session_state.carrinho.values())
        
        # 2. Transparência Cognitiva (Resumo detalhado)
        st.subheader('Confira seu pedido:')
        for sku, qtd in st.session_state.carrinho.items():
            st.write(f'- **{qtd}x** {sku}')
            
        st.markdown(f'**Total de peças:** {total_pecas}')
        st.markdown(f'### Valor a transferir: R$ {valor_total:.2f}')
        
        st.divider()
        
        col_editar, col_gerar_pix = st.columns(2)
        if col_editar.button('Voltar e Editar Pedido'):
            st.session_state.etapa = 1
            st.rerun()

        if col_gerar_pix.button('Confirmar Pedido e Gerar Codigo PIX!', type='primary'):
        # 3. Geração Automática do PIX
            st.session_state.valor_total = valor_total
            st.session_state.etapa = 3
            st.rerun()


    elif st.session_state.etapa == 3:
        st.subheader('Pagamento via PIX')
        valor_total = st.session_state.valor_total
        if gravar_pedido_wide(st.session_state.cliente, st.session_state.carrinho, valor_total):
            st.success('✅ Pedido registrado com sucesso! A diretoria fará a conferência bancária em breve.')
                


            id_rastreio = st.session_state.cliente['telefone'][-4:]
            string_pix = gerar_codigo_pix(valor_total, id_rastreio)
            img_qr = qrcode.make(string_pix)


            st.write(f'Valor total: {valor_total}')
            a, col_qr, v = st.columns([1, 1, 1])
            with col_qr:
                st.image(img_qr.get_image(), caption='Escaneie o QR Code')
            b, col_copia, c = st.columns([1, 8, 1])
            with col_copia:
                st.write('**PIX Copia e Cola:**')
                st.code(string_pix, language='text')
                # --- INÍCIO DO BLOCO DE CÓPIA OTIMIZADO ---
                html_pix = f"""
                <div style="
                    background-color: #1e1e1e;
                    color: #4CAF50;
                    padding: 15px;
                    border-radius: 8px;
                    border: 1px solid #4CAF50;
                    text-align: center;
                    font-family: monospace;
                    font-size: 14px;
                    word-break: break-all;
                    user-select: all; 
                    -webkit-user-select: all; 
                    cursor: pointer;
                ">
                    {string_pix}
                </div>
                <p style="text-align: center; font-size: 14px; margin-top: 5px;">
                    👆 <b>Dê apenas um toque no texto verde acima</b> para selecionar tudo e copiar.
                </p>
                """
                st.markdown(html_pix, unsafe_allow_html=True)
                # --- FIM DO BLOCO ---
                # Reseta a sessão para não travar o celular do usuário se ele quiser fazer outro pedido depois
                # st.session_state.etapa = 1
                # st.session_state.carrinho = {}
                # st.rerun() omitido intencionalmente aqui para permitir a leitura da mensagem de sucesso
            

            st.warning('⚠️ Efetue o pagamento no aplicativo do seu banco.')
        
            st.divider()
