import requests
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

API_TIMEOUT = 20  # Temps limite pour les requêtes API en secondes


class AskiaService:
    BASE_URL = 'https://api.askianet.com/webservice'
    APP_CLIENT = '@iks@TesT0006'
    PV_CODE = '6000'

    @staticmethod
    def call_api(url, params=None, method='GET'):
        headers = {
            'Accept': 'application/json',
            'appClient': AskiaService.APP_CLIENT,
        }

        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
            else:
                response = requests.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"[ASKIA] Erreur API : {e}")
            return {'error': str(e)}
        except ValueError:
            logger.error("[ASKIA] Réponse API invalide (non-JSON)")
            return {'error': 'Réponse JSON invalide'}

    @staticmethod
    def create_client(data):  # Renommer l'argument pour plus de clarté
        url = 'https://api.askianet.com/webservice/srwbclient/createclient'
        params = {
            'pvCode': AskiaService.PV_CODE,
            'nom': data['nom'],
            'pnom': data['prenom'],
            'numtel': data['num_tel'],
            'adresse': data['adresse'],
        }
        response = AskiaService.call_api(url, params)
        logger.info(f"[ASKIA-DEBUG] ➔ Réponse création client : {response}")
        return response
    @staticmethod
    def simulate_auto(vehicule, cli_code, duree, effet):
        url = f"{AskiaService.BASE_URL}/srwb/automobile"
        params = {
            'cat': vehicule.categorie,
            'scatCode': '000',
            'nrg': vehicule.energie,
            'pfs': vehicule.puissance_fiscale,
            'nbP': vehicule.nombre_places,
            'dure': duree,
            'vaf': 10000000,
            'vvn': 4000000,
            'recour': 0, 'avr': 0, 'vol': 0,
            'inc': 0, 'pt': 0, 'gb': 0, 'renv': 0,
            'cliCode': cli_code,
        }
        return AskiaService.call_api(url, params)

    @staticmethod
    def create_contrat(vehicule, cli_code, duree, effet):
        url = f"{AskiaService.BASE_URL}/srwbauto/create"
        params = {
            'cliCode': cli_code,
            'cat': vehicule.categorie,
            'scatCode': '000',
            'carrCode': '07',
            'nrg': vehicule.energie,
            'pfs': vehicule.puissance_fiscale,
            'nbP': vehicule.nombre_places,
            'chrgUtil': 3500,
            'dure': duree,
            'effet': effet,
            'numImmat': vehicule.immatriculation or 'DK1234AA',  # Maintenant dynamique
            'mqCode': vehicule.marque or 'M00427',  # Marque dynamique aussi
            'modele': vehicule.modele,
            'vaf': 0, 'vvn': 0,
            'recour': 0, 'vol': 0, 'inc': 0, 'pt': 0, 'gb': 0
        }
        return AskiaService.call_api(url, params)

    @staticmethod
    def get_document(doc_type, identifier):
        if not identifier:
            return {'error': 'Identifiant manquant'}

        endpoints = {
            'quittance': f"{AskiaService.BASE_URL}/quittance/getfacture?numeroFacture={identifier}",
            'carte_grise': f"{AskiaService.BASE_URL}/quittance/getcartegrise?numeroFacture={identifier}",
            'attestation': f"{AskiaService.BASE_URL}/quittance/getattestation?numeroFacture={identifier}",
        }

        if doc_type not in endpoints:
            return {'error': 'Type de document non supporté'}

        # Ajouter un cache pour éviter des appels répétés
        cache_key = f"document_{doc_type}_{identifier}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        result = AskiaService.call_api(endpoints[doc_type])
        if 'error' not in result:
            cache.set(cache_key, result, timeout=3600)  # Cache pour 1 heure

        return result