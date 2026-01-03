import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'
import { ClaudeAIIcon } from './icons/claude'
import { OllamaIcon } from './icons/ollama'
import { GoogleIcon } from './icons/google'
import { useSettings, useUpdateSettings } from '@renderer/hooks/use-settings'
import { SupportedModels, type SupportedModel } from '@shared/schemas'

type ModelOption = {
  value: SupportedModel
  label: string
  icon: React.ComponentType<{ className?: string }>
}

const modelOptions: ModelOption[] = [
  {
    value: SupportedModels[0],
    label: 'Claude Sonnet 4.5',
    icon: ClaudeAIIcon
  },
  {
    value: SupportedModels[1],
    label: 'Claude Haiku 4.5',
    icon: ClaudeAIIcon
  },
  {
    value: SupportedModels[2],
    label: 'Phi 3.5 (Local)',
    icon: OllamaIcon
  },
  {
    value: SupportedModels[3],
    label: 'DeepSeek R1 (Local)',
    icon: OllamaIcon
  },
  {
    value: SupportedModels[4],
    label: 'Gemma 3 4B (Local)',
    icon: OllamaIcon
  },
  {
    value: SupportedModels[5],
    label: 'T5Gemma 1B (Local)',
    icon: GoogleIcon
  }
]

export function ModelSelector() {
  const { settings } = useSettings()
  const { mutate: updateSettings } = useUpdateSettings()

  const handleValueChange = (value: string) => {
    updateSettings({ selectedModel: value as (typeof modelOptions)[number]['value'] })
  }

  const selectedModel = settings?.selectedModel || modelOptions[0].value

  return (
    <Select value={selectedModel} onValueChange={handleValueChange}>
      <SelectTrigger size="xs" className='border-none dark:bg-input/50 ml-[-4px] mb-[-2px]'>
        <SelectValue>
          {modelOptions.map((option) => {
            if (option.value === selectedModel) {
              const Icon = option.icon
              return (
                <span key={option.value} className="flex items-center gap-1.5">
                  <Icon className="size-3.5" />
                  <span>{option.label}</span>
                </span>
              )
            }
            return null
          })}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className='border-none bg-input/30'>
        {modelOptions.map((option) => {
          const Icon = option.icon
          return (
            <SelectItem key={option.value} value={option.value} size="xs" className='focus:bg-f-800'>
              <Icon className="size-3.5" />
              <span>{option.label}</span>
            </SelectItem>
          )
        })}
      </SelectContent>
    </Select>
  )
}
