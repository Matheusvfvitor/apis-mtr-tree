from fastapi import FastAPI
from fastapi.responses import JSONResponse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import traceback
import time

app = FastAPI()

STEP_DELAY = 1 # ✅ 0,5s entre inputs/ações

def log(msg: str):
    print(f"[IMA-LOGIN] {msg}", flush=True)

def pause(step=STEP_DELAY):
    time.sleep(step)

def iniciar_navegador():
    log("Iniciando navegador (Chrome headless)...")
    options = Options()
    #options.add_argument("--headless=new")  # pode usar "--headless" se preferir
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    log("✅ Driver ready")
    return driver

from selenium.webdriver.common.keys import Keys

def ima_login(cnpj: str, senha: str, unidadeCodigo: str = "", cpf: str = ""):
    driver = iniciar_navegador()
    wait = WebDriverWait(driver, 20)

    try:
        log("Abrindo URL: https://mtr.ima.sc.gov.br/")
        driver.get("https://mtr.ima.sc.gov.br/")
        pause()

        # Seleciona login por CNPJ
        log("Clicando no radio CNPJ (rdCnpj)")
        wait.until(EC.element_to_be_clickable((By.ID, "rdCnpj"))).click()
        pause()

        # -------- CNPJ --------
        log(f"Digitando CNPJ (txtCnpj): {cnpj}")
        cnpj_el = wait.until(EC.presence_of_element_located((By.ID, "txtCnpj")))
        cnpj_el.clear()
        pause()
        cnpj_el.send_keys(cnpj)
        pause()

        # 🔥 Dispara blur via TAB
        log("Disparando blur no CNPJ (TAB)")
        cnpj_el.send_keys(Keys.TAB)
        pause()

        # -------- CPF (campo dinâmico) --------
        log("Aguardando campo CPF (txtCpfUsuario) aparecer")
        cpf_el = wait.until(EC.presence_of_element_located((By.ID, "txtCpfUsuario")))
        log("Campo CPF detectado")

        log(f"Digitando CPF: {cpf}")
        cpf_el.clear()
        pause()
        cpf_el.send_keys(cpf)
        pause()

        # -------- SENHA --------
        log("Digitando senha (txtSenha): ******")
        senha_el = wait.until(EC.presence_of_element_located((By.ID, "txtSenha")))
        senha_el.clear()
        pause()
        senha_el.send_keys(senha)
        pause()

        # -------- LOGIN --------
        log("Clicando no botão Entrar (btEntrar)")
        driver.find_element(By.ID, "btEntrar").click()
        pause()

        # -------- ESPERA PÓS LOGIN --------
        log("Aguardando pós-login: URL conter 'acao=paginaPrincipal'")
        wait.until(EC.url_contains("acao=paginaPrincipal"))

        log(f"✅ Pós-login OK. URL atual: {driver.current_url}")
        pause()

        # -------- COOKIES --------
        cookies_list = driver.get_cookies()
        cookies = {c["name"]: c["value"] for c in cookies_list}

        log(f"✅ Cookies capturados ({len(cookies)}): {cookies}")

        return JSONResponse(
            content={"codigo": 200, "cookies": cookies},
            status_code=200
        )

    except Exception as e:
        log(f"🔴 ERRO: {repr(e)}")
        log(traceback.format_exc())
        return JSONResponse(
            content={"codigo": 900, "erro": repr(e)},
            status_code=500
        )

    finally:
        try:
            driver.quit()
            log("Driver finalizado (quit).")
        except Exception:
            pass

        
ima_login('39.228.967/0001-60','5099ea', '','043.045.326-42')