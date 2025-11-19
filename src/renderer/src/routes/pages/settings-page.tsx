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
import { Label } from '@renderer/components/ui/label'
import { Input } from '@renderer/components/ui/input'

const updateSettingsSchema = z.object({
  preferredName: z.string().min(1, 'Preferred name is required').max(100),
  apiKey: z.string().min(1).max(500).nullable(),
  apiKeyType: z.enum(['openrouter', 'anthropic']).nullable()
})

type SettingsForm = z.infer<typeof updateSettingsSchema>
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

    const result = updateSettingsSchema.safeParse(newData)
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
      <div className="h-32"></div>
      <div className="px-4 py-4 space-y-6">
        <div className="flex items-center justify-between">
          {/* <h2 className="text-lg font-[550] tracking-tight">Settings</h2> */}
          <svg fill="none" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width='48' height='48'>
            {' '}
            <path
              d="M4 5h16v2H4V5zm0 12H2V7h2v10zm16 0v2H4v-2h16zm0 0h2V7h-2v10zm-2-8h-4v6h4V9z"
              fill="currentColor"
            />{' '}
          </svg>
          <SaveIndicator status={saveStatus} />
        </div>
        <div className="flex items-start gap-2">
          <SettingsField
            id="preferredName"
            label="Preferred Name"
            value={formData.preferredName}
            onChange={(value) => validateAndSave('preferredName', value)}
            error={errors.preferredName}
            placeholder="Enter your name"
          />

          <div className="space-y-1.5">
            <Label className="mb-2 text-xs">API Provider</Label>
            <Select
              value={formData.apiKeyType || ''}
              onValueChange={(value) => validateAndSave('apiKeyType', value || null)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openrouter">OpenRouter</SelectItem>
                <SelectItem value="anthropic">Anthropic</SelectItem>
              </SelectContent>
            </Select>
          </div>
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
    <div className="space-y-1.5 flex-grow">
      <Label htmlFor={id} className="mb-2 text-xs">
        {label}
      </Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
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
