import { InputGroup, InputGroupAddon, InputGroupTextarea } from './ui/input-group'
import { ModelSelector } from './model-selector'

export function ComposeMessage() {
  return (
    <div>
      <InputGroup className="border-t border-x-0 border-b-0 min-h-48 rounded-none dark:bg-transparent has-[[data-slot=input-group-control]:focus-visible]:bg-input/15 [[data-slot=input-group-control]:focus-visible]:border-t-f-500">
        <InputGroupTextarea placeholder="Type your message..." rows={3} />
        <InputGroupAddon align="block-end">
          <ModelSelector />
        </InputGroupAddon>
      </InputGroup>
    </div>
  )
}
