from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinLengthValidator
from django.utils.translation import gettext_lazy as _

#========================================================================================================
class Apporteur(models.Model):
    class GradeChoices(models.TextChoices):
        PLATINE = 'platine', _('Platine (18% + 2000 FCFA)')
        FREEMIUM = 'freemium', _('Freemium (10% + 1800 FCFA)')

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name=_("Utilisateur associé"),
        related_name="apporteur"
    )

    telephone = models.CharField(
        max_length=20,
        verbose_name="Téléphone",
        help_text="Numéro de téléphone de l'apporteur"
    )

    adresse = models.CharField(
        max_length=255,
        verbose_name=_("Adresse"),
        validators=[MinLengthValidator(10)],
        help_text=_("Adresse complète de l'apporteur")
    )

    grade = models.CharField(
        max_length=20,
        choices=GradeChoices.choices,
        default=GradeChoices.FREEMIUM,
        verbose_name=_("Grade")
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )

    class Meta:
        verbose_name = _("Apporteur")
        verbose_name_plural = _("Apporteurs")
        ordering = ['-date_creation']
        constraints = [
            models.UniqueConstraint(fields=['user'], name='unique_user_apporteur')
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_grade_display()})"

    @property
    def pourcentage_prime(self):
        return 18 if self.grade == self.GradeChoices.PLATINE else 10

    @property
    def montant_fixe(self):
        return 2000 if self.grade == self.GradeChoices.PLATINE else 1800

    def clean(self):
        if not self.user_id:
            raise ValidationError(_("Un utilisateur doit être associé à l'apporteur"))

    def save(self, *args, **kwargs):
        self.full_clean()  # déclenche clean()
        super().save(*args, **kwargs)

#==================================================================================================================
class Client(models.Model):
    prenom = models.CharField(max_length=100)
    nom = models.CharField(max_length=100)
    adresse = models.CharField(max_length=255)
    num_tel = models.CharField(max_length=20)

    cli_code_askia = models.CharField(max_length=20, blank=True, null=True)  # réponse API

    def __str__(self):
        return f"{self.prenom} {self.nom}"
#=======================================================================================================================
class Vehicule(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="vehicules")
    immatriculation = models.CharField(max_length=100)
    marque = models.CharField(max_length=100)
    modele = models.CharField(max_length=100)
    categorie = models.CharField(max_length=100)
    puissance_fiscale = models.PositiveIntegerField()
    energie = models.CharField(max_length=20, choices=[('E00001', 'Essence'), ('E00002', 'Diesel')])
    nombre_places = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.marque} {self.modele}"

#==================================================================================================================
class Contrat(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE)
    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE)
    apporteur = models.ForeignKey(Apporteur, on_delete=models.SET_NULL, null=True, blank=True)  # <- ici
    duree = models.PositiveIntegerField()
    effet = models.DateField()
    prime_ttc = models.PositiveIntegerField()
    id_saisie = models.CharField(max_length=50)
    numero_police = models.CharField(max_length=100, blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Contrat {self.client} - {self.date_creation.strftime('%d/%m/%Y')}"

#+++++++++++++++++++++++++++++++=================================================================
class PaiementApporteur(models.Model):
    apporteur = models.ForeignKey(Apporteur, on_delete=models.CASCADE)
    contrat = models.OneToOneField(Contrat, on_delete=models.CASCADE, related_name="paiement")
    montant = models.PositiveIntegerField()
    reference = models.CharField(max_length=100, blank=True)
    date_paiement = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.apporteur} - {self.montant} FCFA (Contrat #{self.contrat.id})"


class DocumentContrat(models.Model):
    contrat = models.OneToOneField(Contrat, on_delete=models.CASCADE, related_name='documents')
    quittance = models.JSONField(null=True, blank=True)
    carte_grise = models.JSONField(null=True, blank=True)
    attestation = models.JSONField(null=True, blank=True)

    date_enregistrement = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Documents du contrat {self.contrat.id_saisie}"