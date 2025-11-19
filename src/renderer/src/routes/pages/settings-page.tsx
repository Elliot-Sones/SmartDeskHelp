import { useTitlebar } from '@renderer/hooks/use-titlebar'
import { useSettings, useAutoSaveSettings } from '@renderer/hooks/use-settings'
import { useState, useEffect } from 'react'
import { z } from 'zod'
import { Loader2, AlertCircle } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@renderer/components/ui/select'

const settingsFormSchema = z.object({
  preferredName: z.string().min(1, 'Preferred name is required').max(100),
  apiKey: z.string().min(1).max(500).nullable(),
  apiKeyType: z.enum(['Openrouter', 'Anthropic']).nullable()
})

type SettingsForm = z.infer<typeof settingsFormSchema>
type FieldErrors = Partial<Record<keyof SettingsForm, string>>

export function SettingsPage() {
  useTitlebar({ title: 'Kel — Settings' })

  const { settings, isLoading } = useSettings()
  const { mutate, saveStatus } = useAutoSaveSettings()

  const [formData, setFormData] = useState<SettingsForm>({
    preferredName: '',
    apiKey: null,
    apiKeyType: null
  })
  const [errors, setErrors] = useState<FieldErrors>({})

  // Initialize form data when settings load
  useEffect(() => {
    if (settings) {
      setFormData({
        preferredName: settings.preferredName || '',
        apiKey: settings.apiKey || null,
        apiKeyType: settings.apiKeyType || null
      })
    }
  }, [settings])

  const validateAndSave = (field: keyof SettingsForm, value: string | null) => {
    const newData = { ...formData, [field]: value || null }
    setFormData(newData)

    const result = settingsFormSchema.safeParse(newData)
    if (result.success) {
      setErrors((prev) => ({ ...prev, [field]: undefined }))
      mutate({ [field]: value || null })
    } else {
      const fieldError = result.error.issues.find((e) => e.path[0] === field)
      if (fieldError) {
        setErrors((prev) => ({ ...prev, [field]: fieldError.message }))
      }
    }
  }

  if (isLoading) {
    return (
      <div className="h-20">
        <div className="px-6 py-4 flex items-center justify-center text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="h-20"></div>
      <div className="px-6 py-4 space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-[550] tracking-tight">Settings</h2>
          <SaveIndicator status={saveStatus} />
        </div>

        <SettingsField
          id="preferredName"
          label="Preferred Name"
          value={formData.preferredName}
          onChange={(value) => validateAndSave('preferredName', value)}
          error={errors.preferredName}
          placeholder="Enter your name"
        />

        <div className="space-y-1.5">
          <label className="text-sm font-medium">API Provider</label>
          <Select
            value={formData.apiKeyType || ''}
            onValueChange={(value) => validateAndSave('apiKeyType', value || null)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select provider" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Openrouter">Openrouter</SelectItem>
              <SelectItem value="Anthropic">Anthropic</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <SettingsField
          id="apiKey"
          label="API Key"
          type="password"
          value={formData.apiKey || ''}
          onChange={(value) => validateAndSave('apiKey', value)}
          error={errors.apiKey}
          placeholder="Enter your API key"
        />
      </div>
    </div>
  )
}

function SettingsField({
  id,
  label,
  type = 'text',
  value,
  onChange,
  error,
  placeholder
}: {
  id: string
  label: string
  type?: string
  value: string
  onChange: (value: string) => void
  error?: string
  placeholder: string
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function SaveIndicator({ status }: { status: 'idle' | 'saving' | 'saved' | 'error' }) {
  if (status === 'idle') return null

  if (status === 'saved') {
    return <div className="text-xs text-muted-foreground">Saved</div>
  }

  const config = {
    saving: { icon: Loader2, text: 'Saving...', className: 'text-muted-foreground', animate: true },
    error: {
      icon: AlertCircle,
      text: 'Error saving',
      className: 'text-destructive',
      animate: false
    }
  }

  const { icon: Icon, text, className, animate } = config[status]

  return (
    <div className={`flex items-center gap-1.5 text-xs ${className}`}>
      <Icon className={`h-3.5 w-3.5 ${animate ? 'animate-spin' : ''}`} />
      <span>{text}</span>
    </div>
  )
}
