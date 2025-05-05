from django.urls import path
from . import views
from .views import dashboard_apporteur, dashboard_admin
from .views import get_marques_htmx, get_categories_htmx

urlpatterns = [
    path('', views.home, name='home'),
    path('connexion/', views.custom_login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('nv/', views.client_vehicule_view, name='client_vehicule'),
    path('cli/sim/', views.client_simulation_view, name='client_simulation'),
    path('co/ac/', views.achat_contrat_view, name='achat_contrat'),
    path('co/doc/<int:contrat_id>/', views.documents_contrat_view, name='documents_contrat'),
    path('ap/dashboard/', dashboard_apporteur, name='dashboard_apporteur'),
    path('dashboard/', dashboard_admin, name='dashboard_admin'),
    path('profil/<int:apporteur_id>/', views.profil_apporteur_view, name='profil_apporteur'),
    path('pm/', views.paiement_apporteur_view, name='paiement_apporteur_admin'),
    path('ap/no/', views.creer_apporteur, name='creer_apporteur'),
    path('ap/doc/', views.historique_documents_apporteur, name='historique_documents_apporteur'),
    path('ajax/marques/', get_marques_htmx, name='get_marques'),
    path('ajax/categories/', get_categories_htmx, name='get_categories'),
    path('ap/export/excel/', views.export_documents_excel, name='export_documents_excel'),
    path('contrat/<int:contrat_id>/renouveler/', views.renouveler_contrat_view, name='renouveler_contrat'),
]

