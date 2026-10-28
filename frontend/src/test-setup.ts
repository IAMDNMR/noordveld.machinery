import { configure } from '@testing-library/react'

// Testing Library waits 1 s by default; under a loaded parallel run the Spark conversation tests need longer.
configure({ asyncUtilTimeout: 5000 })
