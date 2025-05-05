from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Client, Vehicule, Apporteur

# ============================== CLIENT ==============================
class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['prenom', 'nom', 'adresse', 'num_tel']
        labels = {
            'num_tel': 'Téléphone',
            'prenom': 'Prénom'
        }

# ============================== VEHICULE ==============================
class VehiculeForm(forms.ModelForm):
    class Meta:
        model = Vehicule
        fields = ['immatriculation', 'marque', 'modele', 'categorie', 'puissance_fiscale', 'energie', 'nombre_places']
        labels = {
            'modele': 'Modèle',
            'nombre_places': 'Nombre de places',
        }

# ============================== SIMULATION ==============================
DUREES = [
    (1, '1 mois'),
    (3, '3 mois'),
    (6, '6 mois'),
    (12, '12 mois'),
]

class SimulationForm(forms.Form):
    duree = forms.ChoiceField(
        choices=DUREES,
        label="Durée du contrat",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    effet = forms.DateField(
        label="Date d’effet",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )

# ============================== APPORTEUR ==============================
class ApporteurForm(forms.ModelForm):
    prenom = forms.CharField(
        label="Prénom",
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom'})
    )
    nom = forms.CharField(
        label="Nom",
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom'})
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@exemple.com'})
    )
    mot_de_passe = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'}),
        validators=[validate_password]
    )
    confirmation_mot_de_passe = forms.CharField(
        label="Confirmation du mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'})
    )
    telephone = forms.CharField(
        label="Téléphone",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '77XXXXXXX'})
    )
    grade = forms.ChoiceField(
        choices=Apporteur.GradeChoices.choices,
        label="Grade",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Apporteur
        fields = ['adresse', 'grade', 'telephone']
        widgets = {
            'adresse': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Adresse complète'}),
        }
        labels = {
            'adresse': "Adresse",
        }

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Cet email est déjà utilisé.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('mot_de_passe') != cleaned_data.get('confirmation_mot_de_passe'):
            self.add_error('confirmation_mot_de_passe', "Les mots de passe ne correspondent pas.")
        return cleaned_data

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['email'],
            email=self.cleaned_data['email'],
            password=self.cleaned_data['mot_de_passe'],
            first_name=self.cleaned_data['prenom'],
            last_name=self.cleaned_data['nom']
        )

        apporteur = super().save(commit=False)
        apporteur.user = user
        apporteur.telephone = self.cleaned_data['telephone']

        if commit:
            user.save()
            apporteur.save()

        return apporteur
