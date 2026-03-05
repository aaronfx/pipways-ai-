function initEditor(data = {}) {
    editor = new EditorJS({
        holder: 'editorjs',
        data: data,
        tools: {
            header: {
                class: Header,
                config: {
                    levels: [1, 2, 3, 4, 5, 6],
                    defaultLevel: 1
                }
            },
            paragraph: {
                class: Paragraph,
                inlineToolbar: true
            },
            list: {
                class: List,
                inlineToolbar: true
            },
            quote: {
                class: Quote,
                inlineToolbar: true
            },
            table: {
                class: Table,
                inlineToolbar: true
            },
            code: CodeTool,
            image: {
                class: ImageTool,
                config: {
                    uploader: {
                        uploadByFile(file) {
                            return new Promise((resolve, reject) => {
                                const formData = new FormData();
                                formData.append('file', file);
                                
                                fetch(API_URL + '/media/upload', {
                                    method: 'POST',
                                    headers: {'Authorization': 'Bearer ' + authToken},
                                    body: formData
                                })
                                .then(res => res.json())
                                .then(data => {
                                    if (data.success) {
                                        resolve({
                                            success: 1,
                                            file: {url: API_URL + data.url}
                                        });
                                    } else {
                                        reject('Upload failed');
                                    }
                                })
                                .catch(reject);
                            });
                        }
                    }
                }
            },
            embed: {
                class: Embed,
                config: {
                    services: {
                        tradingview: true,
                        youtube: true,
                        vimeo: true
                    }
                }
            },
            delimiter: Delimiter
        }
    });
}
