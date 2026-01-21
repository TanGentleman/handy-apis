# Evaluating JavaScript

## Introduction[​](#introduction)

Playwright scripts run in your Playwright environment. Your page scripts run in the browser page environment. Those environments don't intersect, they are running in different virtual machines in different processes and even potentially on different computers.

The [page.evaluate()](/python/docs/api/class-page#page-evaluate) API can run a JavaScript function in the context of the web page and bring results back to the Playwright environment. Browser globals like `window` and `document` can be used in `evaluate`.

- Sync
- Async

```
href = page.evaluate('() => document.location.href')

```

```
href = await page.evaluate('() => document.location.href')

```

If the result is a Promise or if the function is asynchronous evaluate will automatically wait until it's resolved:

- Sync
- Async

```
status = page.evaluate("""async () => {
  response = await fetch(location.href)
  return response.status
}""")

```

```
status = await page.evaluate("""async () => {
  response = await fetch(location.href)
  return response.status
}""")

```

## Different environments[​](#different-environments)

Evaluated scripts run in the browser environment, while your test runs in a testing environments. This means you cannot use variables from your test in the page and vice versa. Instead, you should pass them explicitly as an argument.

The following snippet is **WRONG** because it uses the variable directly:

- Sync
- Async

```
data = "some data"
result = page.evaluate("""() => {
  // WRONG: there is no "data" in the web page.
  window.myApp.use(data)
}""")

```

```
data = "some data"
result = await page.evaluate("""() => {
  // WRONG: there is no "data" in the web page.
  window.myApp.use(data)
}""")

```

The following snippet is **CORRECT** because it passes the value explicitly as an argument:

- Sync
- Async

```
data = "some data"
# Pass |data| as a parameter.
result = page.evaluate("""data => {
  window.myApp.use(data)
}""", data)

```

```
data = "some data"
# Pass |data| as a parameter.
result = await page.evaluate("""data => {
  window.myApp.use(data)
}""", data)

```

## Evaluation Argument[​](#evaluation-argument)

Playwright evaluation methods like [page.evaluate()](/python/docs/api/class-page#page-evaluate) take a single optional argument. This argument can be a mix of [Serializable](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/JSON/stringify#Description) values and [JSHandle](/python/docs/api/class-jshandle) instances. Handles are automatically converted to the value they represent.

- Sync
- Async

```
# A primitive value.
page.evaluate('num => num', 42)

# An array.
page.evaluate('array => array.length', [1, 2, 3])

# An object.
page.evaluate('object => object.foo', { 'foo': 'bar' })

# A single handle.
button = page.evaluate_handle('window.button')
page.evaluate('button => button.textContent', button)

# Alternative notation using JSHandle.evaluate.
button.evaluate('(button, from) => button.textContent.substring(from)', 5)

# Object with multiple handles.
button1 = page.evaluate_handle('window.button1')
button2 = page.evaluate_handle('.button2')
page.evaluate("""o => o.button1.textContent + o.button2.textContent""",
    { 'button1': button1, 'button2': button2 })

# Object destructuring works. Note that property names must match
# between the destructured object and the argument.
# Also note the required parenthesis.
page.evaluate("""
    ({ button1, button2 }) => button1.textContent + button2.textContent""",
    { 'button1': button1, 'button2': button2 })

# Array works as well. Arbitrary names can be used for destructuring.
# Note the required parenthesis.
page.evaluate("""
    ([b1, b2]) => b1.textContent + b2.textContent""",
    [button1, button2])

# Any mix of serializables and handles works.
page.evaluate("""
    x => x.button1.textContent + x.list[0].textContent + String(x.foo)""",
    { 'button1': button1, 'list': [button2], 'foo': None })

```

```
# A primitive value.
await page.evaluate('num => num', 42)

# An array.
await page.evaluate('array => array.length', [1, 2, 3])

# An object.
await page.evaluate('object => object.foo', { 'foo': 'bar' })

# A single handle.
button = await page.evaluate_handle('button')
await page.evaluate('button => button.textContent', button)

# Alternative notation using JSHandle.evaluate.
await button.evaluate('(button, from) => button.textContent.substring(from)', 5)

# Object with multiple handles.
button1 = await page.evaluate_handle('window.button1')
button2 = await page.evaluate_handle('window.button2')
await page.evaluate("""
    o => o.button1.textContent + o.button2.textContent""",
    { 'button1': button1, 'button2': button2 })

# Object destructuring works. Note that property names must match
# between the destructured object and the argument.
# Also note the required parenthesis.
await page.evaluate("""
    ({ button1, button2 }) => button1.textContent + button2.textContent""",
    { 'button1': button1, 'button2': button2 })

# Array works as well. Arbitrary names can be used for destructuring.
# Note the required parenthesis.
await page.evaluate("""
    ([b1, b2]) => b1.textContent + b2.textContent""",
    [button1, button2])

# Any mix of serializables and handles works.
await page.evaluate("""
    x => x.button1.textContent + x.list[0].textContent + String(x.foo)""",
    { 'button1': button1, 'list': [button2], 'foo': None })

```

## Init scripts[​](#init-scripts)

Sometimes it is convenient to evaluate something in the page before it starts loading. For example, you might want to setup some mocks or test data.

In this case, use [page.add_init_script()](/python/docs/api/class-page#page-add-init-script) or [browser_context.add_init_script()](/python/docs/api/class-browsercontext#browser-context-add-init-script). In the example below, we will replace `Math.random()` with a constant value.

First, create a `preload.js` file that contains the mock.

```
// preload.js
Math.random = () => 42;

```

Next, add init script to the page.

- Sync
- Async

```
# In your test, assuming the "preload.js" file is in the "mocks" directory.
page.add_init_script(path="mocks/preload.js")

```

```
# In your test, assuming the "preload.js" file is in the "mocks" directory.
await page.add_init_script(path="mocks/preload.js")

```