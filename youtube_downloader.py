import os
import yt_dlp
import time

# Garante que a pasta de downloads exista para evitar erro "File Not Found"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads", "youtube")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_youtube_file(url, quality="1080", to_mp3=False, cookiefile=None):
    """
    Função principal. Executada em thread pelo bot.py para não travar o Telegram.
    Lida perfeitamente com conversão MP3, limites de resolução e Cookies do Render.
    """
    agora = int(time.time())
    # Cria um nome de arquivo temporário seguro
    output_template = os.path.join(DOWNLOAD_DIR, f"{agora}_%(id)s.%(ext)s")

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'noplaylist': True,
    }

    # Injeta o cookie exportado do seu Base64 no Render, se existir
    if cookiefile and os.path.exists(cookiefile):
        ydl_opts['cookiefile'] = cookiefile

    # Tratamento para download de Áudio (Botão MP3)
    if to_mp3:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    # Tratamento para download de Vídeo (Resolução selecionada)
    else:
        # Tenta baixar na qualidade escolhida. Se não tiver, pega a melhor disponível abaixo dela
        ydl_opts['format'] = f'bestvideo[ext=mp4][height<={quality}]+bestaudio[ext=m4a]/bestvideo[height<={quality}]+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Pega o caminho exato onde o yt-dlp salvou o arquivo final
            filepath = ydl.prepare_filename(info)
            if to_mp3:
                # Se for MP3, ajustamos a extensão final do arquivo retornado
                filepath = filepath.rsplit('.', 1)[0] + '.mp3'
                
            return filepath
            
    except Exception as e:
        raise Exception(f"{e}")

# Função de compatibilidade (Fallback) caso o bot tente usar a chamada antiga async
async def baixar_video_youtube(url, output_dir, chat_id=None):
    import asyncio
    loop = asyncio.get_running_loop()
    # Roda a função síncrona em uma thread separada para não congelar o bot
    return await loop.run_in_executor(None, lambda: download_youtube_file(url, quality="1080"))
