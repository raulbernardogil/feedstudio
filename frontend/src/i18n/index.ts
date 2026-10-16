import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { es } from './es'

// Spanish is the initial language; add resources here to support more locales.
void i18n.use(initReactI18next).init({
  resources: { es: { translation: es } },
  lng: 'es',
  fallbackLng: 'es',
  interpolation: { escapeValue: false }, // React already escapes rendered values
})

export default i18n
