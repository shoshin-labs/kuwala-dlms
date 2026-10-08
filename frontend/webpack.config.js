const path = require('path');
const CopyWebpackPlugin = require('copy-webpack-plugin');
const HtmlWebpackPlugin = require('html-webpack-plugin')
const TerserPlugin = require('terser-webpack-plugin');

module.exports = {
    mode: 'development',
    devtool: 'source-map',
    entry: ["babel-polyfill", './src/js/index.tsx'],
    node: {
        fs: 'empty'
    },
    output: {
        filename: 'js/[name].[hash].bundle.js',
        path: path.resolve(__dirname, 'static'),
        publicPath: "/static/",
        hashFunction: 'sha256'
    },
    resolve: {
        extensions: ['.ts', '.tsx', '.js']
    },
    optimization: {
        // This Webpack 4 plugin's disk cache uses MD4, unavailable in modern
        // OpenSSL. Disable only that cache; SHA-256 handles emitted asset hashes.
        minimizer: [new TerserPlugin({ cache: false, parallel: true, sourceMap: true })]
    },
    module: {
        rules: [{
            test: /\.(ts|js)x?$/,
            exclude: /node_modules/,
            use: {
                loader: 'babel-loader',
            }
        },{
            test: /\.css$/,
            use: [ 'style-loader', 'css-loader' ]
        },{
            test: /\.(png|svg|jpg|gif)$/,
            use: [{
                loader: 'file-loader',
                options: { name: '[sha256:hash:hex:20].[ext]' }
            }]
        },{
            test: /\.html$/,
            use: ['html-loader']
        }]
    },
    plugins: [
        new HtmlWebpackPlugin({
            inject: 'body',
            template: path.join(__dirname, "src/html/index.html")
        }),
        new CopyWebpackPlugin([
            {
                from: 'css/**/*',
            },
            {
                from: 'images/**/*',
            },
        ], {
            context: 'src/'
        })
    ],
};
