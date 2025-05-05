import logging
from datetime import date
import xlwt
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import transaction
from django.template.loader import render_to_string
from django.contrib.auth import authenticate, login, logout
from django.utils.timezone import now
from .models import Vehicule, Contrat, Apporteur, PaiementApporteur, DocumentContrat
from .forms import ClientForm, VehiculeForm, SimulationForm, ApporteurForm
from .services import AskiaService
from django.db.models import Sum, Q
from django.utils.dateparse import parse_date
from django.db.models import Exists, OuterRef

logger = logging.getLogger(__name__)

# =========================== HOME ===========================
@login_required
def home(request):
    return render(request, 'core/home.html')
# =================== CLIENT + VEHICULE ======================
@login_required
def client_vehicule_view(request):
    client_form = ClientForm(request.POST or None)
    vehicule_form = VehiculeForm(request.POST or None)

    if request.method == "POST" and client_form.is_valid() and vehicule_form.is_valid():
        try:
            with transaction.atomic():
                # Création du client en base locale
                client = client_form.save()

                # Appel API Askia pour créer le client distant
                response = AskiaService.create_client({
                    'nom': client.nom,
                    'prenom': client.prenom,
                    'num_tel': client.num_tel,
                    'adresse': client.adresse,
                })

                logger.debug(f"Réponse Askia création client: {response}")

                if 'error' in response:
                    raise Exception(response['error'])

                cli_code = response.get('cliCode') or response.get('cliNumero')
                if not cli_code:
                    raise Exception("Aucun code client reçu d'Askia.")

                # Mise à jour du client avec cliCode Askia
                client.cli_code_askia = cli_code
                client.save()

                # Création du véhicule
                vehicule = vehicule_form.save(commit=False)
                vehicule.client = client
                vehicule.save()

                # Enregistrement dans la session
                request.session['cliCode_askia'] = cli_code
                request.session['vehicule_id'] = vehicule.id
                request.session.modified = True

                messages.success(request, "Client et véhicule enregistrés. Passez à la simulation.")
                return redirect('client_simulation')

        except Exception as e:
            logger.error(f"Erreur lors de la création du client/véhicule: {str(e)}", exc_info=True)
            messages.error(request, f"Erreur: {str(e)}")

    return render(request, 'core/client_vehicule_form.html', {
        'client_form': client_form,
        'vehicule_form': vehicule_form,
        'today': now().date().isoformat()
    })
#=====================================================================================================================
@login_required
def client_simulation_view(request):
    cli_code = request.session.get('cliCode_askia')
    vehicule_id = request.session.get('vehicule_id')
    if not cli_code or not vehicule_id:
        messages.error(request, "Session expirée. Recommencez.")
        return redirect('client_vehicule')

    vehicule = get_object_or_404(Vehicule.objects.select_related('client'), id=vehicule_id)
    client = vehicule.client

    form = SimulationForm(request.POST or None)
    simulation_result = None
    achat_result = None

    # Récupérer les marques et catégories depuis l'API
    marques = AskiaService.call_api("https://api.askianet.com/webservice/referentiel/marques")
    categories = AskiaService.call_api(
        "https://api.askianet.com/webservice/referentiel/categories", {'brCode': '500'}
    )

    # Créer des dictionnaires pour la correspondance code -> nom
    marque_map = {m['code']: m['libelle'] for m in marques if 'code' in m and 'libelle' in m}
    categorie_map = {c['code']: c['libelle'] for c in categories if 'code' in c and 'libelle' in c}

    # Traduire les codes en noms
    marque_nom = marque_map.get(vehicule.marque, vehicule.marque)  # Retourne le nom ou le code si non trouvé
    categorie_nom = categorie_map.get(vehicule.categorie, vehicule.categorie)

    # Logique pour le bouton "Confirmer l'achat"
    if request.method == "POST" and 'acheter' in request.POST:
        if not request.session.get('achat_duree') or not request.session.get('achat_effet'):
            messages.error(request, "Veuillez d'abord effectuer une simulation.")
            return render(request, 'core/client_simulation.html', {
                'client': client,
                'vehicule': vehicule,
                'cli_code': cli_code,
                'form': form,
                'simulation_result': simulation_result,
                'achat_result': achat_result,
                'marque_nom': marque_nom,
                'categorie_nom': categorie_nom
            })
        return redirect('achat_contrat')

    elif request.method == "POST" and 'simuler' in request.POST:
        if form.is_valid():
            try:
                duree = form.cleaned_data['duree']
                effet = form.cleaned_data['effet']
                response = AskiaService.simulate_auto(vehicule, cli_code, duree, effet.strftime('%d/%m/%Y'))
                if 'error' in response:
                    raise Exception(response['error'])
                simulation_result = response
                request.session['achat_duree'] = duree
                request.session['achat_effet'] = effet.isoformat()
                messages.success(request, "Simulation réussie.")
            except Exception as e:
                logger.error(f"Erreur Simulation: {str(e)}", exc_info=True)
                messages.error(request, f"Erreur: {str(e)}")

    return render(request, 'core/client_simulation.html', {
        'client': client,
        'vehicule': vehicule,
        'cli_code': cli_code,
        'form': form,
        'simulation_result': simulation_result,
        'achat_result': achat_result,
        'marque_nom': marque_nom,
        'categorie_nom': categorie_nom
    })
# Fonction utilitaire pour le calcul du paiement des apporteurs
def calculer_paiement_apporteur(contrat):
    if contrat.apporteur:
        montant = int((contrat.prime_ttc * contrat.apporteur.pourcentage_prime) / 100) + contrat.apporteur.montant_fixe

        PaiementApporteur.objects.create(
            apporteur=contrat.apporteur,
            contrat=contrat,
            montant=montant,
            reference=f"{contrat.apporteur.id}-{contrat.id_saisie}"
        )
        return montant
    return 0
#=====================================================================================================
@login_required
def achat_contrat_view(request):
    vehicule_id = request.session.get('vehicule_id')
    cli_code = request.session.get('cliCode_askia')

    if not vehicule_id or not cli_code:
        messages.error(request, "Session expirée.")
        return redirect('client_vehicule')

    vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    client = vehicule.client

    duree = request.session.get('achat_duree')
    effet_str = request.session.get('achat_effet')

    if not duree or not effet_str:
        messages.error(request, "Simulation manquante.")
        return redirect('client_simulation')

    effet_date = parse_date(effet_str)

    try:
        contrat_data = AskiaService.create_contrat(
            vehicule, cli_code, effet=effet_date.strftime('%d/%m/%Y'), duree=duree
        )

        if 'error' in contrat_data:
            raise Exception(contrat_data['error'])

        with transaction.atomic():
            apporteur = getattr(request.user, 'apporteur', None)

            contrat = Contrat.objects.create(
                client=client,
                vehicule=vehicule,
                duree=duree,
                effet=effet_date,
                prime_ttc=contrat_data.get('primettc', 0),
                id_saisie=contrat_data.get('idSaisie', ''),
                numero_police=contrat_data.get('numeroPolice', ''),
                apporteur=apporteur
            )

            # Paiement admin selon grade
            if apporteur:
                montant = int((contrat.prime_ttc * apporteur.pourcentage_prime) / 100) + apporteur.montant_fixe
                PaiementApporteur.objects.create(
                    apporteur=apporteur,
                    contrat=contrat,
                    montant=montant,
                    reference=f"AP-{apporteur.id}-{contrat.id_saisie}"
                )

            # 🔄 Appels documents pour stockage local
            quittance = AskiaService.get_document('quittance', cli_code)
            carte_grise = AskiaService.get_document('carte_grise', contrat.id_saisie)
            attestation = AskiaService.get_document('attestation', contrat.id_saisie)

            if isinstance(quittance, dict) and isinstance(carte_grise, dict) and isinstance(attestation, dict):
                DocumentContrat.objects.create(
                    contrat=contrat,
                    quittance=quittance,
                    carte_grise=carte_grise,
                    attestation=attestation
                )

        request.session.pop('achat_duree', None)
        request.session.pop('achat_effet', None)
        messages.success(request, f"Contrat {contrat.id_saisie} créé avec succès.")
        return redirect('documents_contrat', contrat.id)

    except Exception as e:
        logger.exception("Erreur lors de l'achat")
        messages.error(request, f"Erreur: {e}")
        return redirect('client_simulation')

#=====================================================================================================
@login_required
def documents_contrat_view(request, contrat_id):
    contrat = get_object_or_404(Contrat, id=contrat_id)

    documents = getattr(contrat, 'documents', None)

    if documents:
        quittance = documents.quittance
        carte_grise_data = documents.carte_grise
        attestation_data = documents.attestation
    else:
        quittance = AskiaService.get_document('quittance', contrat.client.cli_code_askia)
        carte_grise_data = AskiaService.get_document('carte_grise', contrat.id_saisie)
        attestation_data = AskiaService.get_document('attestation', contrat.id_saisie)

        if isinstance(quittance, dict) and isinstance(carte_grise_data, dict) and isinstance(attestation_data, dict):
            with transaction.atomic():
                DocumentContrat.objects.create(
                    contrat=contrat,
                    quittance=quittance,
                    carte_grise=carte_grise_data,
                    attestation=attestation_data
                )

    # ✅ Correction ici : liens extraits depuis les bons champs
    liens = attestation_data.get('lien', {}) if isinstance(attestation_data, dict) else {}

    return render(request, 'core/documents_contrat.html', {
        'contrat': contrat,
        'quittance': quittance,
        'carte_grise': carte_grise_data,
        'attestation': attestation_data,
        'lien_attestation': liens.get('linkAttestation'),
        'lien_cartebrune': liens.get('linkCarteBrune'),
    })


# dashboard_apporteur======================================================
@login_required
def dashboard_apporteur(request):
    try:
        apporteur = Apporteur.objects.get(user=request.user)
    except Apporteur.DoesNotExist:
        return render(request, 'core/erreur.html', {'message': "Vous n'êtes pas un apporteur."})

    contrats_list = Contrat.objects.filter(apporteur=apporteur).annotate(
        is_paye=Exists(PaiementApporteur.objects.filter(contrat=OuterRef('pk')))
    ).order_by('-date_creation')

    paginator = Paginator(contrats_list, 10)
    page_number = request.GET.get('page', 1)
    contrats = paginator.get_page(page_number)

    total_primes = sum([c.prime_ttc for c in contrats_list])
    commission = (total_primes * apporteur.pourcentage_prime) / 100

    return render(request, 'core/dashboard_apporteur.html', {
        'apporteur': apporteur,
        'contrats': contrats,
        'total_primes': total_primes,
        'commission': commission
    })

##### Paiement apporteur==================================================================================================
@staff_member_required
def paiement_apporteur_view(request, contrat_id): # Assurez-vous que votre vue reçoit l'ID du contrat
    message = None

    if request.method == 'POST':
        apporteur_id = request.POST.get('apporteur_id')
        montant = request.POST.get('montant')
        reference = request.POST.get('reference', '')

        # Validation des données
        if not apporteur_id or not montant:
            message = "Veuillez remplir tous les champs obligatoires."
        else:
            try:
                apporteur = Apporteur.objects.get(id=apporteur_id)
                montant = int(montant)
                contrat = Contrat.objects.get(id=contrat_id) # Récupérer l'objet Contrat

                # Vérifier si le contrat a déjà été payé
                if PaiementApporteur.objects.filter(contrat=contrat).exists():
                    messages.error(request, "Ce contrat a déjà été payé.")
                    return redirect('paiement_apporteur_admin') # Rediriger vers la liste des paiements ou une autre page appropriée
                else:
                    if montant <= 0:
                        message = "Le montant doit être supérieur à 0."
                    else:
                        # Création du paiement avec transaction
                        with transaction.atomic():
                            PaiementApporteur.objects.create(
                                apporteur=apporteur,
                                montant=montant,
                                reference=reference,
                                contrat=contrat # Associer le paiement au contrat
                            )
                            logger.info(f"Paiement créé pour l'apporteur {apporteur.id} (contrat {contrat.id}): {montant}")
                            messages.success(request, "Le paiement a été enregistré avec succès.")
                            return redirect('paiement_apporteur_admin') # Rediriger après un paiement réussi

            except Apporteur.DoesNotExist:
                message = "Apporteur non trouvé."
            except Contrat.DoesNotExist:
                message = "Contrat non trouvé."
            except ValueError:
                message = "Le montant doit être un nombre entier."
            except Exception as e:
                logger.error(f"Erreur lors de la création du paiement: {e}")
                message = f"Une erreur est survenue: {str(e)}"

    apporteurs = Apporteur.objects.all()
    paiements = PaiementApporteur.objects.all().order_by('-date_paiement')

    return render(request, 'core/admin_paiements.html', {
        'apporteurs': apporteurs,
        'paiements': paiements,
        'message': message
    })
#=======================================================================================================================
@staff_member_required
def dashboard_admin(request):
    # Filtres dynamiques
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    id_apporteur = request.GET.get('apporteur')

    contrats = Contrat.objects.select_related('apporteur', 'client', 'vehicule')

    # Filtres date
    if date_debut:
        date_d = parse_date(date_debut)
        if date_d:
            contrats = contrats.filter(date_creation__gte=date_d)
    if date_fin:
        date_f = parse_date(date_fin)
        if date_f:
            contrats = contrats.filter(date_creation__lte=date_f)

    # Filtre par apporteur
    if id_apporteur:
        contrats = contrats.filter(apporteur__id=id_apporteur)

    # Statistiques globales
    stats = {
        'total_contrats': contrats.count(),
        'total_primes': contrats.aggregate(Sum('prime_ttc'))['prime_ttc__sum'] or 0,
    }

    # Commissions par apporteur
    commissions = []
    for a in Apporteur.objects.select_related('user'):
        contrats_a = contrats.filter(apporteur=a)
        primes_a = contrats_a.aggregate(Sum('prime_ttc'))['prime_ttc__sum'] or 0
        commission = round((primes_a * a.pourcentage_prime) / 100 + (contrats_a.count() * a.montant_fixe), 0)
        commissions.append({
            'apporteur': a,
            'nb_contrats': contrats_a.count(),
            'primes': primes_a,
            'commission': commission
        })

    # Ajoute un champ virtuel : contrat déjà payé ?
    contrats = contrats.annotate(
        is_paye=Exists(PaiementApporteur.objects.filter(contrat=OuterRef('pk')))
    )

    contrats_recents = contrats.order_by('-date_creation')[:5]

    return render(request, 'core/dashboard_admin.html', {
        'contrats': contrats,
        'stats': stats,
        'commissions': commissions,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'liste_apporteurs': Apporteur.objects.select_related('user'),
        'contrats_recents': contrats_recents,
    })

# --- Marques depuis Askia ---
def get_marques_htmx(request):
    marques = AskiaService.call_api("https://api.askianet.com/webservice/referentiel/marques")

    if 'error' in marques:
        marques = []
        logger.error(f"Erreur lors de la récupération des marques: {marques.get('error')}")

    html = render_to_string("core/components/select_marques.html", {"marques": marques})
    return HttpResponse(html)
# --- Catégories depuis Askia ---
def get_categories_htmx(request):
    categories = AskiaService.call_api(
        "https://api.askianet.com/webservice/referentiel/categories",
        {'brCode': '500'}
    )

    if 'error' in categories:
        categories = []
        logger.error(f"Erreur lors de la récupération des catégories: {categories.get('error')}")

    html = render_to_string("core/components/select_categories.html", {"categories": categories})
    return HttpResponse(html)
#===========================================================================================================
@login_required
def historique_documents_apporteur(request):
    try:
        apporteur = Apporteur.objects.get(user=request.user)
    except Apporteur.DoesNotExist:
        return render(request, 'core/erreur.html', {'message': "Vous n'êtes pas un apporteur."})

    search = request.GET.get('search', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    contrats = Contrat.objects.filter(apporteur=apporteur)

    # Recherche texte
    if search:
        contrats = contrats.filter(
            Q(client__nom__icontains=search) |
            Q(client__prenom__icontains=search) |
            Q(id_saisie__icontains=search) |
            Q(vehicule__modele__icontains=search)
        )

    # Filtres par date
    if date_debut:
        d1 = parse_date(date_debut)
        if d1:
            contrats = contrats.filter(effet__gte=d1)

    if date_fin:
        d2 = parse_date(date_fin)
        if d2:
            contrats = contrats.filter(effet__lte=d2)

    contrats = contrats.select_related('client', 'vehicule').order_by('-date_creation')

    page = request.GET.get('page', 1)
    paginator = Paginator(contrats, 10)

    try:
        contrats_page = paginator.page(page)
    except PageNotAnInteger:
        contrats_page = paginator.page(1)
    except EmptyPage:
        contrats_page = paginator.page(paginator.num_pages)

    return render(request, 'core/historique_documents.html', {
        'contrats': contrats_page,
        'apporteur': apporteur,
        'search': search,
        'date_debut': date_debut,
        'date_fin': date_fin,
    })


# Exporter document en excel===================================================================
@login_required
def export_documents_excel(request):
    try:
        apporteur = Apporteur.objects.get(user=request.user)
    except Apporteur.DoesNotExist:
        return render(request, 'core/erreur.html', {'message': "Vous n'êtes pas un apporteur."})

    contrats = Contrat.objects.filter(apporteur=apporteur).order_by('-date_creation')

    response = HttpResponse(content_type='application/ms-excel')
    response['Content-Disposition'] = 'attachment; filename="documents_apporteur.xls"'

    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Contrats')

    # Style pour l'en-tête
    header_style = xlwt.easyxf('font: bold on')

    # En-tête
    row_num = 0
    columns = ['Client', 'Véhicule', 'Date Effet', 'Prime TTC', 'ID Saisie']

    for col_num, column_title in enumerate(columns):
        ws.write(row_num, col_num, column_title, header_style)

    # Contenu
    for contrat in contrats:
        row_num += 1
        client_name = f"{contrat.client.prenom} {contrat.client.nom}" if contrat.client else "N/A"
        vehicule_info = f"{contrat.vehicule.marque} {contrat.vehicule.modele}" if contrat.vehicule else "N/A"
        effet_date = contrat.effet.strftime('%d/%m/%Y') if contrat.effet else "N/A"

        ws.write(row_num, 0, client_name)
        ws.write(row_num, 1, vehicule_info)
        ws.write(row_num, 2, effet_date)
        ws.write(row_num, 3, contrat.prime_ttc)
        ws.write(row_num, 4, contrat.id_saisie or "N/A")

    wb.save(response)
    return response


# Authentification================================================================
def custom_login_view(request):
    message = ""
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")

        if not username or not password:
            message = "Veuillez remplir tous les champs."
        else:
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                logger.info(f"Utilisateur {username} connecté")

                if user.is_staff or user.is_superuser:
                    return redirect('dashboard_admin')

                try:
                    apporteur = Apporteur.objects.get(user=user)
                    return redirect('dashboard_apporteur')
                except Apporteur.DoesNotExist:
                    logger.warning(f"Utilisateur {username} connecté mais n'est pas un apporteur")
                    return render(request, 'core/erreur.html',
                                  {'message': "Vous n'êtes pas autorisé à accéder au système."})
            else:
                logger.warning(f"Échec de connexion pour l'utilisateur {username}")
                message = "Identifiants incorrects."

    return render(request, 'core/login.html', {'message': message})


# Logout==================================================================================
def logout_view(request):
    if request.user.is_authenticated:
        username = request.user.username
        logout(request)
        logger.info(f"Utilisateur {username} déconnecté")
    return redirect('login')


# Creer apporteur==============================================================================
@staff_member_required
def creer_apporteur(request):
    if request.method == 'POST':
        form = ApporteurForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "✅ Apporteur créé avec succès !")
                return redirect('dashboard_admin')
            except Exception as e:
                logger.exception("Erreur lors de la création de l'apporteur.")
                messages.error(request, f"Erreur technique : {e}")
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = ApporteurForm()

    return render(request, 'core/creer_apporteur.html', {'form': form})
#==========================================================================================================================
@login_required
def renouveler_contrat_view(request, contrat_id):
    ancien_contrat = get_object_or_404(Contrat, id=contrat_id, apporteur__user=request.user)

    # Copie du véhicule et nouveau contrat
    try:
        with transaction.atomic():
            nouveau_contrat = Contrat.objects.create(
                client=ancien_contrat.client,
                vehicule=ancien_contrat.vehicule,
                effet=date.today(),
                duree=ancien_contrat.duree,
                apporteur=ancien_contrat.apporteur,
                prime_ttc=0,  # Recalculé plus tard
            )
            messages.info(request, "Le contrat a été préparé pour renouvellement. Vous pouvez maintenant le simuler.")
            request.session['cliCode_askia'] = ancien_contrat.client.cli_code_askia
            request.session['vehicule_id'] = ancien_contrat.vehicule.id
            return redirect('client_simulation')
    except Exception as e:
        logger.exception("Erreur renouvellement contrat")
        messages.error(request, f"Erreur : {e}")
        return redirect('dashboard_apporteur')
@staff_member_required
def profil_apporteur_view(request, apporteur_id):
    apporteur = get_object_or_404(Apporteur.objects.select_related('user'), id=apporteur_id)

    # Contrats de l'apporteur
    contrats = Contrat.objects.filter(apporteur=apporteur).order_by('-date_creation')

    # Paiements liés
    paiements = PaiementApporteur.objects.filter(apporteur=apporteur).order_by('-date_paiement')

    # Statistiques
    total_primes = contrats.aggregate(Sum('prime_ttc'))['prime_ttc__sum'] or 0
    total_commission = sum(p.montant for p in paiements)

    return render(request, 'core/profil_apporteur.html', {
        'apporteur': apporteur,
        'contrats': contrats,
        'paiements': paiements,
        'total_primes': total_primes,
        'total_commission': total_commission,
        'nombre_contrats': contrats.count()
    })
