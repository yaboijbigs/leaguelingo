from django import forms
from .models import LeagueMemberEmail, League

class LeagueMemberEmailForm(forms.ModelForm):
    class Meta:
        model = LeagueMemberEmail
        fields = ['email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter email address'})

class CustomizeWriterForm(forms.ModelForm):
    class Meta:
        model = League
        fields = ['custom_system_prompt']
        widgets = {
            'custom_system_prompt': forms.Textarea(attrs={
                'class': 'form-control',
                #'placeholder': 'Lorem ipsum dolor sit amet, consectetuer adipiscing elit. Aenean commodo ligula eget dolor. Aenean massa. Cum sociis natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus. Donec quam felis, ultricies nec, pellentesque eu, pretium quis, sem. Nulla consequat massa quis enim. Donec pede justo, fringilla vel, aliquet nec, vulputate eget, arcu. In enim justo, rhoncus ut, imperdiet a, venenatis vitae, justo. Nullam dictum felis eu pede mollis pretium. Integer tincidunt. Cras dapibu',
                'placeholder': 'Simply tell the Sports Writer the style/tone/voice you want it to adapt and your future newsletters will follow those instructions. For example, if you want it to trash talk more frequently, you can say "Talk more trash and be more extremely aggressive, feel free to use swear words." If you want the Sports Writer to consistently mention how awful the Chicago Bears are, you can say "Frequently mention how awful the Chicago Bears." If you want newsletters in a different language, simply say "Write the newsletters in Spanish (or any language you want)." Get creative and have fun with it!',
                'rows': 5,  # Adjust the number of rows to your preference
                'cols': 40,  # Optional: Adjust the number of columns
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

from django import forms

class SupportForm(forms.Form):
    email = forms.EmailField(required=True, label='Your Email')
    phone = forms.CharField(required=False, label='Phone Number', max_length=15)
    league_id = forms.CharField(required=False, label='League ID', max_length=50)
    complaint = forms.CharField(
        widget=forms.Textarea(attrs={'maxlength': 2000}),
        label='Complaint',
        max_length=2000,
        required=True
    )

class ScheduleForm(forms.Form):
    DAYS_OF_WEEK = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]
    day = forms.ChoiceField(choices=DAYS_OF_WEEK)
    time = forms.TimeField(widget=forms.TimeInput(format='%H:%M'))