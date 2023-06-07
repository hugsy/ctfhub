window.addEventListener('DOMContentLoaded', (event) => {
            var formatSelect = document.getElementById('id_format');
            var dataTextArea = document.getElementById('id_data');

            formatSelect.addEventListener('change', function () {
                var selectedFormat = this.value;
                var placeholderText;

                switch (selectedFormat) {
                    case 'RAW':
                        placeholderText = 'name | category';
                        break;
                    case 'CTFd':
                        placeholderText = 'paste CTFd JSON /api/v1/challenges';
                        break;
                    case 'rCTF':
                        placeholderText = 'paste rCTF JSON /api/v1/challs';
                        break;
                    default:
                        placeholderText = '';
                }

                dataTextArea.setAttribute('placeholder', placeholderText);
            });

            // Trigger the change event on page load to set initial placeholder
            formatSelect.dispatchEvent(new Event('change'));
});