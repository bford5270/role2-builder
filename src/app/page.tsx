import { useState } from 'react'
import { supabase } from '../lib/supabase'

function CaseAuthor() {
  const [caseData, setCaseData] = useState({
    // Basic Info
    title: '',
    chiefComplaint: '',
    
    // Demographics
    patientAgeYears: '',
    patientAgeMonths: 0,
    patientSex: 'male',
    
    // History
    hpi: '',
    pmh: '',
    psh: '',
    medications: '',
    allergies: '',
    familyHistory: '',
    socialHistory: '',
    ros: '',
    
    // Diagnosis
    correctDiagnosis: '',
  })

  const [vitals, setVitals] = useState({
    heartRate: '',
    respiratoryRate: '',
    systolicBp: '',
    diastolicBp: '',
    temperature: '',
    o2Saturation: '',
    weightKg: '',
    heightCm: '',
    painScore: '',
    notes: '',
  })

  const [physicalExam, setPhysicalExam] = useState({
    // General
    generalAppearance: '',
    generalDistress: false,
    generalNotes: '',
    
    // Head
    headNormocephalic: true,
    headAtraumatic: true,
    headFindings: '',
    
    // Eyes
    eyesPupilsEqual: true,
    eyesPupilsReactive: true,
    eyesConjunctiva: 'normal',
    eyesSclera: 'normal',
    eyesEom: 'intact',
    eyesFindings: '',
    
    // ENT
    entEars: '',
    entNose: '',
    entOropharynx: 'normal',
    entTympanicMembranes: '',
    entFindings: '',
    
    // Neck
    neckSupple: true,
    neckJvd: false,
    neckThyromegaly: false,
    neckLymphadenopathy: false,
    neckCarotidBruits: false,
    neckFindings: '',
    
    // Lungs
    lungsClearBilaterally: true,
    lungsWheezes: false,
    lungsRales: false,
    lungsRhonchi: false,
    lungsDiminished: false,
    lungsLocation: '',
    lungsFindings: '',
    
    // Cardiovascular
    cvRegularRate: true,
    cvRegularRhythm: true,
    cvMurmur: false,
    cvMurmurDescription: '',
    cvRub: false,
    cvGallop: false,
    cvFindings: '',
    
    // Abdomen
    abdSoft: true,
    abdNontender: true,
    abdNondistended: true,
    abdBowelSounds: 'normal',
    abdMasses: false,
    abdHepatomegaly: false,
    abdSplenomegaly: false,
    abdRebound: false,
    abdGuarding: false,
    abdTendernessLocation: '',
    abdFindings: '',
    
    // Extremities
    extremEdema: false,
    extremEdemaLocation: '',
    extremCyanosis: false,
    extremClubbing: false,
    extremDeformities: false,
    extremFindings: '',
    
    // Peripheral Vascular
    periphVascPulses: '2+ throughout',
    periphVascCapillaryRefill: '<2 seconds',
    periphVascFindings: '',
    
    // Skin
    skinWarm: true,
    skinDry: true,
    skinRash: false,
    skinRashDescription: '',
    skinLesions: false,
    skinLesionsDescription: '',
    skinJaundice: false,
    skinFindings: '',
    
    // Neurological
    neuroAlert: true,
    neuroOriented: 'x3',
    neuroCranialNerves: 'II-XII intact',
    neuroMotorStrength: '5/5 throughout',
    neuroSensory: 'intact to light touch',
    neuroReflexes: '2+ symmetric',
    neuroGait: 'normal',
    neuroCerebellar: 'intact',
    neuroFindings: '',
  })

  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState({ type: '', text: '' })
  const [expandedSections, setExpandedSections] = useState({
    demographics: true,
    vitals: true,
    history: true,
    physicalExam: false,
    diagnosis: true,
  })

  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setMessage({ type: '', text: '' })

    try {
      // Insert case
      const { data: caseResult, error: caseError } = await supabase
        .from('cases')
        .insert([
          {
            title: caseData.title,
            chief_complaint: caseData.chiefComplaint,
            patient_age_years: parseInt(caseData.patientAgeYears),
            patient_age_months: parseInt(caseData.patientAgeMonths) || 0,
            patient_sex: caseData.patientSex,
            hpi: caseData.hpi,
            pmh: caseData.pmh,
            psh: caseData.psh,
            medications: caseData.medications,
            allergies: caseData.allergies,
            family_history: caseData.familyHistory,
            social_history: caseData.socialHistory,
            ros: caseData.ros,
            correct_diagnosis: caseData.correctDiagnosis,
          }
        ])
        .select()

      if (caseError) throw caseError

      const caseId = caseResult[0].id

      // Insert vital signs
      const { error: vitalsError } = await supabase
        .from('case_vital_signs')
        .insert([
          {
            case_id: caseId,
            heart_rate: vitals.heartRate ? parseInt(vitals.heartRate) : null,
            respiratory_rate: vitals.respiratoryRate ? parseInt(vitals.respiratoryRate) : null,
            systolic_bp: vitals.systolicBp ? parseInt(vitals.systolicBp) : null,
            diastolic_bp: vitals.diastolicBp ? parseInt(vitals.diastolicBp) : null,
            temperature: vitals.temperature ? parseFloat(vitals.temperature) : null,
            o2_saturation: vitals.o2Saturation ? parseInt(vitals.o2Saturation) : null,
            weight_kg: vitals.weightKg ? parseFloat(vitals.weightKg) : null,
            height_cm: vitals.heightCm ? parseFloat(vitals.heightCm) : null,
            pain_score: vitals.painScore ? parseInt(vitals.painScore) : null,
            notes: vitals.notes,
          }
        ])

      if (vitalsError) throw vitalsError

      // Insert physical exam
      const { error: examError } = await supabase
        .from('case_physical_exam')
        .insert([
          {
            case_id: caseId,
            general_appearance: physicalExam.generalAppearance,
            general_distress: physicalExam.generalDistress,
            general_notes: physicalExam.generalNotes,
            head_normocephalic: physicalExam.headNormocephalic,
            head_atraumatic: physicalExam.headAtraumatic,
            head_findings: physicalExam.headFindings,
            eyes_pupils_equal: physicalExam.eyesPupilsEqual,
            eyes_pupils_reactive: physicalExam.eyesPupilsReactive,
            eyes_conjunctiva: physicalExam.eyesConjunctiva,
            eyes_sclera: physicalExam.eyesSclera,
            eyes_eom: physicalExam.eyesEom,
            eyes_findings: physicalExam.eyesFindings,
            ent_ears: physicalExam.entEars,
            ent_nose: physicalExam.entNose,
            ent_oropharynx: physicalExam.entOropharynx,
            ent_tympanic_membranes: physicalExam.entTympanicMembranes,
            ent_findings: physicalExam.entFindings,
            neck_supple: physicalExam.neckSupple,
            neck_jvd: physicalExam.neckJvd,
            neck_thyromegaly: physicalExam.neckThyromegaly,
            neck_lymphadenopathy: physicalExam.neckLymphadenopathy,
            neck_carotid_bruits: physicalExam.neckCarotidBruits,
            neck_findings: physicalExam.neckFindings,
            lungs_clear_bilaterally: physicalExam.lungsClearBilaterally,
            lungs_wheezes: physicalExam.lungsWheezes,
            lungs_rales: physicalExam.lungsRales,
            lungs_rhonchi: physicalExam.lungsRhonchi,
            lungs_diminished: physicalExam.lungsDiminished,
            lungs_location: physicalExam.lungsLocation,
            lungs_findings: physicalExam.lungsFindings,
            cv_regular_rate: physicalExam.cvRegularRate,
            cv_regular_rhythm: physicalExam.cvRegularRhythm,
            cv_murmur: physicalExam.cvMurmur,
            cv_murmur_description: physicalExam.cvMurmurDescription,
            cv_rub: physicalExam.cvRub,
            cv_gallop: physicalExam.cvGallop,
            cv_findings: physicalExam.cvFindings,
            abd_soft: physicalExam.abdSoft,
            abd_nontender: physicalExam.abdNontender,
            abd_nondistended: physicalExam.abdNondistended,
            abd_bowel_sounds: physicalExam.abdBowelSounds,
            abd_masses: physicalExam.abdMasses,
            abd_hepatomegaly: physicalExam.abdHepatomegaly,
            abd_splenomegaly: physicalExam.abdSplenomegaly,
            abd_rebound: physicalExam.abdRebound,
            abd_guarding: physicalExam.abdGuarding,
            abd_tenderness_location: physicalExam.abdTendernessLocation,
            abd_findings: physicalExam.abdFindings,
            extrem_edema: physicalExam.extremEdema,
            extrem_edema_location: physicalExam.extremEdemaLocation,
            extrem_cyanosis: physicalExam.extremCyanosis,
            extrem_clubbing: physicalExam.extremClubbing,
            extrem_deformities: physicalExam.extremDeformities,
            extrem_findings: physicalExam.extremFindings,
            periph_vasc_pulses: physicalExam.periphVascPulses,
            periph_vasc_capillary_refill: physicalExam.periphVascCapillaryRefill,
            periph_vasc_findings: physicalExam.periphVascFindings,
            skin_warm: physicalExam.skinWarm,
            skin_dry: physicalExam.skinDry,
            skin_rash: physicalExam.skinRash,
            skin_rash_description: physicalExam.skinRashDescription,
            skin_lesions: physicalExam.skinLesions,
            skin_lesions_description: physicalExam.skinLesionsDescription,
            skin_jaundice: physicalExam.skinJaundice,
            skin_findings: physicalExam.skinFindings,
            neuro_alert: physicalExam.neuroAlert,
            neuro_oriented: physicalExam.neuroOriented,
            neuro_cranial_nerves: physicalExam.neuroCranialNerves,
            neuro_motor_strength: physicalExam.neuroMotorStrength,
            neuro_sensory: physicalExam.neuroSensory,
            neuro_reflexes: physicalExam.neuroReflexes,
            neuro_gait: physicalExam.neuroGait,
            neuro_cerebellar: physicalExam.neuroCerebellar,
            neuro_findings: physicalExam.neuroFindings,
          }
        ])

      if (examError) throw examError

      // Success!
      setMessage({ 
        type: 'success', 
        text: 'Case saved successfully!' 
      })
      
      // Clear form
      setCaseData({
        title: '',
        chiefComplaint: '',
        patientAgeYears: '',
        patientAgeMonths: 0,
        patientSex: 'male',
        hpi: '',
        pmh: '',
        psh: '',
        medications: '',
        allergies: '',
        familyHistory: '',
        socialHistory: '',
        ros: '',
        correctDiagnosis: '',
      })
      
      setVitals({
        heartRate: '',
        respiratoryRate: '',
        systolicBp: '',
        diastolicBp: '',
        temperature: '',
        o2Saturation: '',
        weightKg: '',
        heightCm: '',
        painScore: '',
        notes: '',
      })

      console.log('Case saved with ID:', caseId)
    } catch (error) {
      console.error('Error saving case:', error)
      setMessage({ 
        type: 'error', 
        text: `Error: ${error.message}` 
      })
    } finally {
      setLoading(false)
    }
  }

  const SectionHeader = ({ title, section, children }) => (
    <div className="bg-primary-50 border border-primary-200 rounded-lg p-4 mb-4">
      <button
        type="button"
        onClick={() => toggleSection(section)}
        className="w-full flex justify-between items-center text-left"
      >
        <h2 className="text-xl font-semibold text-primary-900">{title}</h2>
        <span className="text-primary-600 text-2xl">
          {expandedSections[section] ? '−' : '+'}
        </span>
      </button>
      {expandedSections[section] && (
        <div className="mt-4 space-y-4">
          {children}
        </div>
      )}
    </div>
  )

  const CheckboxField = ({ label, checked, onChange, name }) => (
    <label className="flex items-center space-x-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(name, e.target.checked)}
        className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
      />
      <span className="text-sm text-gray-700">{label}</span>
    </label>
  )

  return (
    <div className="max-w-6xl mx-auto pb-20">
      <div className="bg-white rounded-lg shadow-md p-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Create New Case
        </h1>
        <p className="text-gray-600 mb-6">
          Complete all sections to create a comprehensive diagnostic case
        </p>

        {message.text && (
          <div className={`mb-6 p-4 rounded-md ${
            message.type === 'success' 
              ? 'bg-green-50 border border-green-200 text-green-800' 
              : 'bg-red-50 border border-red-200 text-red-800'
          }`}>
            {message.text}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Information */}
          <div className="bg-gray-50 p-4 rounded-lg">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Basic Information</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Case Title *
                </label>
                <input
                  type="text"
                  required
                  value={caseData.title}
                  onChange={(e) => setCaseData({ ...caseData, title: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="e.g., 45-year-old male with chest pain"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Chief Complaint *
                </label>
                <input
                  type="text"
                  required
                  value={caseData.chiefComplaint}
                  onChange={(e) => setCaseData({ ...caseData, chiefComplaint: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="e.g., Chest pain for 2 hours"
                />
              </div>
            </div>
          </div>

          {/* Demographics */}
          <SectionHeader title="Patient Demographics" section="demographics">
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Age (Years) *
                </label>
                <input
                  type="number"
                  required
                  min="0"
                  max="120"
                  value={caseData.patientAgeYears}
                  onChange={(e) => setCaseData({ ...caseData, patientAgeYears: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Age (Months)
                </label>
                <input
                  type="number"
                  min="0"
                  max="11"
                  value={caseData.patientAgeMonths}
                  onChange={(e) => setCaseData({ ...caseData, patientAgeMonths: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="For pediatric cases"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Sex
                </label>
                <select
                  value={caseData.patientSex}
                  onChange={(e) => setCaseData({ ...caseData, patientSex: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </div>
          </SectionHeader>

          {/* Vital Signs */}
          <SectionHeader title="Initial Vital Signs" section="vitals">
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Heart Rate (bpm)
                </label>
                <input
                  type="number"
                  value={vitals.heartRate}
                  onChange={(e) => setVitals({ ...vitals, heartRate: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Respiratory Rate (breaths/min)
                </label>
                <input
                  type="number"
                  value={vitals.respiratoryRate}
                  onChange={(e) => setVitals({ ...vitals, respiratoryRate: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Temperature (°C)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={vitals.temperature}
                  onChange={(e) => setVitals({ ...vitals, temperature: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Systolic BP (mmHg)
                </label>
                <input
                  type="number"
                  value={vitals.systolicBp}
                  onChange={(e) => setVitals({ ...vitals, systolicBp: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Diastolic BP (mmHg)
                </label>
                <input
                  type="number"
                  value={vitals.diastolicBp}
                  onChange={(e) => setVitals({ ...vitals, diastolicBp: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  O2 Saturation (%)
                </label>
                <input
                  type="number"
                  value={vitals.o2Saturation}
                  onChange={(e) => setVitals({ ...vitals, o2Saturation: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Weight (kg)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={vitals.weightKg}
                  onChange={(e) => setVitals({ ...vitals, weightKg: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Height (cm)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={vitals.heightCm}
                  onChange={(e) => setVitals({ ...vitals, heightCm: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Pain Score (0-10)
                </label>
                <input
                  type="number"
                  min="0"
                  max="10"
                  value={vitals.painScore}
                  onChange={(e) => setVitals({ ...vitals, painScore: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Vital Signs Notes
              </label>
              <input
                type="text"
                value={vitals.notes}
                onChange={(e) => setVitals({ ...vitals, notes: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g., on 2L O2, after morphine"
              />
            </div>
          </SectionHeader>

          {/* Patient History */}
          <SectionHeader title="Patient History" section="history">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                History of Present Illness (HPI) *
              </label>
              <textarea
                required
                value={caseData.hpi}
                onChange={(e) => setCaseData({ ...caseData, hpi: e.target.value })}
                rows="4"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Onset, location, duration, character, alleviating/aggravating factors..."
              />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Past Medical History (PMH)
                </label>
                <textarea
                  value={caseData.pmh}
                  onChange={(e) => setCaseData({ ...caseData, pmh: e.target.value })}
                  rows="3"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Chronic conditions, previous diagnoses..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Past Surgical History (PSH)
                </label>
                <textarea
                  value={caseData.psh}
                  onChange={(e) => setCaseData({ ...caseData, psh: e.target.value })}
                  rows="3"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Previous surgeries..."
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Medications
              </label>
              <textarea
                value={caseData.medications}
                onChange={(e) => setCaseData({ ...caseData, medications: e.target.value })}
                rows="3"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Current medications with doses..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Allergies
              </label>
              <input
                type="text"
                value={caseData.allergies}
                onChange={(e) => setCaseData({ ...caseData, allergies: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g., NKDA, Penicillin (rash)"
              />
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Family History (FH)
                </label>
                <textarea
                  value={caseData.familyHistory}
                  onChange={(e) => setCaseData({ ...caseData, familyHistory: e.target.value })}
                  rows="2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Social History (SH)
                </label>
                <textarea
                  value={caseData.socialHistory}
                  onChange={(e) => setCaseData({ ...caseData, socialHistory: e.target.value })}
                  rows="2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Tobacco, alcohol, occupation..."
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Review of Systems (ROS)
              </label>
              <textarea
                value={caseData.ros}
                onChange={(e) => setCaseData({ ...caseData, ros: e.target.value })}
                rows="4"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Constitutional, HEENT, CV, Resp, GI, GU, MSK, Neuro, Psych..."
              />
            </div>
          </SectionHeader>

          {/* Physical Exam - Collapsed by default due to size */}
          <SectionHeader title="Physical Examination" section="physicalExam">
            {/* General */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">General Appearance</h3>
              <div className="space-y-3">
                <input
                  type="text"
                  value={physicalExam.generalAppearance}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, generalAppearance: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="e.g., Well-appearing, no acute distress"
                />
                <CheckboxField
                  label="In distress"
                  checked={physicalExam.generalDistress}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, generalDistress: value })}
                  name="generalDistress"
                />
                <textarea
                  value={physicalExam.generalNotes}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, generalNotes: e.target.value })}
                  rows="2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Additional general findings..."
                />
              </div>
            </div>

            {/* Head */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Head</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Normocephalic"
                  checked={physicalExam.headNormocephalic}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, headNormocephalic: value })}
                />
                <CheckboxField
                  label="Atraumatic"
                  checked={physicalExam.headAtraumatic}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, headAtraumatic: value })}
                />
              </div>
              <textarea
                value={physicalExam.headFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, headFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional head findings..."
              />
            </div>

            {/* Eyes */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Eyes</h3>
              <div className="grid md:grid-cols-2 gap-3 mb-3">
                <CheckboxField
                  label="Pupils equal"
                  checked={physicalExam.eyesPupilsEqual}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, eyesPupilsEqual: value })}
                />
                <CheckboxField
                  label="Pupils reactive"
                  checked={physicalExam.eyesPupilsReactive}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, eyesPupilsReactive: value })}
                />
              </div>
              <div className="grid md:grid-cols-3 gap-3 mb-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Conjunctiva</label>
                  <input
                    type="text"
                    value={physicalExam.eyesConjunctiva}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, eyesConjunctiva: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="normal, pale, injected"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Sclera</label>
                  <input
                    type="text"
                    value={physicalExam.eyesSclera}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, eyesSclera: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="normal, icteric"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">EOM</label>
                  <input
                    type="text"
                    value={physicalExam.eyesEom}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, eyesEom: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="intact, limited"
                  />
                </div>
              </div>
              <textarea
                value={physicalExam.eyesFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, eyesFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Additional eye findings..."
              />
            </div>

            {/* ENT */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">ENT (Ears, Nose, Throat)</h3>
              <div className="grid md:grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Ears</label>
                  <input
                    type="text"
                    value={physicalExam.entEars}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, entEars: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Nose</label>
                  <input
                    type="text"
                    value={physicalExam.entNose}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, entNose: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Oropharynx</label>
                  <input
                    type="text"
                    value={physicalExam.entOropharynx}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, entOropharynx: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="normal, erythematous, exudates"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Tympanic Membranes</label>
                  <input
                    type="text"
                    value={physicalExam.entTympanicMembranes}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, entTympanicMembranes: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                  />
                </div>
              </div>
              <textarea
                value={physicalExam.entFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, entFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="Additional ENT findings..."
              />
            </div>

            {/* Neck */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Neck</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Supple"
                  checked={physicalExam.neckSupple}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, neckSupple: value })}
                />
                <CheckboxField
                  label="JVD"
                  checked={physicalExam.neckJvd}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, neckJvd: value })}
                />
                <CheckboxField
                  label="Thyromegaly"
                  checked={physicalExam.neckThyromegaly}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, neckThyromegaly: value })}
                />
                <CheckboxField
                  label="Lymphadenopathy"
                  checked={physicalExam.neckLymphadenopathy}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, neckLymphadenopathy: value })}
                />
                <CheckboxField
                  label="Carotid bruits"
                  checked={physicalExam.neckCarotidBruits}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, neckCarotidBruits: value })}
                />
              </div>
              <textarea
                value={physicalExam.neckFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, neckFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional neck findings..."
              />
            </div>

            {/* Lungs */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Lungs / Respiratory</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Clear to auscultation bilaterally"
                  checked={physicalExam.lungsClearBilaterally}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, lungsClearBilaterally: value })}
                />
                <CheckboxField
                  label="Wheezes"
                  checked={physicalExam.lungsWheezes}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, lungsWheezes: value })}
                />
                <CheckboxField
                  label="Rales/Crackles"
                  checked={physicalExam.lungsRales}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, lungsRales: value })}
                />
                <CheckboxField
                  label="Rhonchi"
                  checked={physicalExam.lungsRhonchi}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, lungsRhonchi: value })}
                />
                <CheckboxField
                  label="Diminished breath sounds"
                  checked={physicalExam.lungsDiminished}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, lungsDiminished: value })}
                />
              </div>
              <input
                type="text"
                value={physicalExam.lungsLocation}
                onChange={(e) => setPhysicalExam({ ...physicalExam, lungsLocation: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Location (e.g., bilateral bases, right upper lobe)"
              />
              <textarea
                value={physicalExam.lungsFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, lungsFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional lung findings..."
              />
            </div>

            {/* Cardiovascular */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Cardiovascular</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Regular rate"
                  checked={physicalExam.cvRegularRate}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, cvRegularRate: value })}
                />
                <CheckboxField
                  label="Regular rhythm"
                  checked={physicalExam.cvRegularRhythm}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, cvRegularRhythm: value })}
                />
                <CheckboxField
                  label="Murmur"
                  checked={physicalExam.cvMurmur}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, cvMurmur: value })}
                />
                <CheckboxField
                  label="Rub"
                  checked={physicalExam.cvRub}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, cvRub: value })}
                />
                <CheckboxField
                  label="Gallop (S3/S4)"
                  checked={physicalExam.cvGallop}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, cvGallop: value })}
                />
              </div>
              {physicalExam.cvMurmur && (
                <input
                  type="text"
                  value={physicalExam.cvMurmurDescription}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, cvMurmurDescription: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                  placeholder="Murmur description (e.g., systolic 3/6 at apex)"
                />
              )}
              <textarea
                value={physicalExam.cvFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, cvFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional cardiovascular findings..."
              />
            </div>

            {/* Abdomen */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Abdomen</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Soft"
                  checked={physicalExam.abdSoft}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdSoft: value })}
                />
                <CheckboxField
                  label="Non-tender"
                  checked={physicalExam.abdNontender}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdNontender: value })}
                />
                <CheckboxField
                  label="Non-distended"
                  checked={physicalExam.abdNondistended}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdNondistended: value })}
                />
                <CheckboxField
                  label="Masses"
                  checked={physicalExam.abdMasses}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdMasses: value })}
                />
                <CheckboxField
                  label="Hepatomegaly"
                  checked={physicalExam.abdHepatomegaly}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdHepatomegaly: value })}
                />
                <CheckboxField
                  label="Splenomegaly"
                  checked={physicalExam.abdSplenomegaly}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdSplenomegaly: value })}
                />
                <CheckboxField
                  label="Rebound"
                  checked={physicalExam.abdRebound}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdRebound: value })}
                />
                <CheckboxField
                  label="Guarding"
                  checked={physicalExam.abdGuarding}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, abdGuarding: value })}
                />
              </div>
              <div className="mt-3 space-y-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Bowel Sounds</label>
                  <input
                    type="text"
                    value={physicalExam.abdBowelSounds}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, abdBowelSounds: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="normal, hyperactive, hypoactive, absent"
                  />
                </div>
                <input
                  type="text"
                  value={physicalExam.abdTendernessLocation}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, abdTendernessLocation: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Tenderness location (e.g., RLQ, epigastrium)"
                />
                <textarea
                  value={physicalExam.abdFindings}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, abdFindings: e.target.value })}
                  rows="2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Additional abdominal findings..."
                />
              </div>
            </div>

            {/* Extremities */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Extremities</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Edema"
                  checked={physicalExam.extremEdema}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, extremEdema: value })}
                />
                <CheckboxField
                  label="Cyanosis"
                  checked={physicalExam.extremCyanosis}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, extremCyanosis: value })}
                />
                <CheckboxField
                  label="Clubbing"
                  checked={physicalExam.extremClubbing}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, extremClubbing: value })}
                />
                <CheckboxField
                  label="Deformities"
                  checked={physicalExam.extremDeformities}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, extremDeformities: value })}
                />
              </div>
              {physicalExam.extremEdema && (
                <input
                  type="text"
                  value={physicalExam.extremEdemaLocation}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, extremEdemaLocation: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                  placeholder="Edema location (e.g., bilateral lower extremities)"
                />
              )}
              <textarea
                value={physicalExam.extremFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, extremFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional extremity findings..."
              />
            </div>

            {/* Peripheral Vascular */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Peripheral Vascular</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Pulses</label>
                  <input
                    type="text"
                    value={physicalExam.periphVascPulses}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, periphVascPulses: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="e.g., 2+ throughout, diminished DP bilaterally"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Capillary Refill</label>
                  <input
                    type="text"
                    value={physicalExam.periphVascCapillaryRefill}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, periphVascCapillaryRefill: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="e.g., <2 seconds, delayed"
                  />
                </div>
                <textarea
                  value={physicalExam.periphVascFindings}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, periphVascFindings: e.target.value })}
                  rows="2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="Additional vascular findings..."
                />
              </div>
            </div>

            {/* Skin */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Skin</h3>
              <div className="grid md:grid-cols-2 gap-3">
                <CheckboxField
                  label="Warm"
                  checked={physicalExam.skinWarm}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, skinWarm: value })}
                />
                <CheckboxField
                  label="Dry"
                  checked={physicalExam.skinDry}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, skinDry: value })}
                />
                <CheckboxField
                  label="Rash"
                  checked={physicalExam.skinRash}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, skinRash: value })}
                />
                <CheckboxField
                  label="Lesions"
                  checked={physicalExam.skinLesions}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, skinLesions: value })}
                />
                <CheckboxField
                  label="Jaundice"
                  checked={physicalExam.skinJaundice}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, skinJaundice: value })}
                />
              </div>
              {physicalExam.skinRash && (
                <input
                  type="text"
                  value={physicalExam.skinRashDescription}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, skinRashDescription: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                  placeholder="Rash description"
                />
              )}
              {physicalExam.skinLesions && (
                <input
                  type="text"
                  value={physicalExam.skinLesionsDescription}
                  onChange={(e) => setPhysicalExam({ ...physicalExam, skinLesionsDescription: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                  placeholder="Lesion description"
                />
              )}
              <textarea
                value={physicalExam.skinFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, skinFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional skin findings..."
              />
            </div>

            {/* Neurological */}
            <div className="border-l-4 border-primary-300 pl-4">
              <h3 className="font-semibold text-gray-900 mb-3">Neurological</h3>
              <div className="grid md:grid-cols-2 gap-3 mb-3">
                <CheckboxField
                  label="Alert"
                  checked={physicalExam.neuroAlert}
                  onChange={(name, value) => setPhysicalExam({ ...physicalExam, neuroAlert: value })}
                />
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Oriented</label>
                  <input
                    type="text"
                    value={physicalExam.neuroOriented}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroOriented: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="x3, x2, x1, x0"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Cranial Nerves</label>
                  <input
                    type="text"
                    value={physicalExam.neuroCranialNerves}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroCranialNerves: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="II-XII intact"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Motor Strength</label>
                  <input
                    type="text"
                    value={physicalExam.neuroMotorStrength}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroMotorStrength: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="5/5 throughout"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Sensory</label>
                  <input
                    type="text"
                    value={physicalExam.neuroSensory}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroSensory: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="intact to light touch"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Reflexes</label>
                  <input
                    type="text"
                    value={physicalExam.neuroReflexes}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroReflexes: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="2+ symmetric"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Gait</label>
                  <input
                    type="text"
                    value={physicalExam.neuroGait}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroGait: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="normal, antalgic"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Cerebellar</label>
                  <input
                    type="text"
                    value={physicalExam.neuroCerebellar}
                    onChange={(e) => setPhysicalExam({ ...physicalExam, neuroCerebellar: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    placeholder="intact, dysmetria"
                  />
                </div>
              </div>
              <textarea
                value={physicalExam.neuroFindings}
                onChange={(e) => setPhysicalExam({ ...physicalExam, neuroFindings: e.target.value })}
                rows="2"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 mt-3"
                placeholder="Additional neurological findings..."
              />
            </div>
          </SectionHeader>

          {/* Diagnosis */}
          <SectionHeader title="Diagnosis" section="diagnosis">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Correct Diagnosis *
              </label>
              <input
                type="text"
                required
                value={caseData.correctDiagnosis}
                onChange={(e) => setCaseData({ ...caseData, correctDiagnosis: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="e.g., Acute myocardial infarction (STEMI)"
              />
            </div>
          </SectionHeader>

          {/* Action Buttons */}
          <div className="flex gap-4 pt-6 border-t sticky bottom-0 bg-white py-4">
            <button
              type="submit"
              disabled={loading}
              className={`bg-primary-600 text-white px-8 py-3 rounded-md hover:bg-primary-700 transition-colors font-medium text-lg ${
                loading ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              {loading ? 'Saving...' : 'Save Case'}
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              disabled={loading}
              className="bg-gray-200 text-gray-700 px-8 py-3 rounded-md hover:bg-gray-300 transition-colors font-medium text-lg"
            >
              Clear All
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CaseAuthor
