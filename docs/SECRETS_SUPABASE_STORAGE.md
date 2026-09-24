# Secrets necessárias para fotos no Supabase Storage

Na hospedagem Streamlit, configure:

[ supabase ]

url = "https://vgabxdprocwmpmhoxrgt.supabase.co"
service_role_key = "SUA_SERVICE_ROLE_KEY"

A chave service_role é somente de servidor. Não colocar no código, GitHub,
HTML, JavaScript ou qualquer valor enviado ao navegador.

O módulo `supabase_storage.py` usa essa credencial apenas no servidor para
enviar/baixar arquivos do bucket `patrimonio-fotos`.

A chave nunca deve ser commitada no repositório.
